import os
import re
import asyncio
import logging
from pathlib import Path
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TOKEN = os.environ.get("BOT_TOKEN")
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO)

WELCOME = """
🔥 **بوت Coin YE الجبار V2** 🔥

أرسل أي رابط واختار الجودة اللي تبيها!

📱 تيك توك (بدون علامة)
📸 انستا | فيسبوك
🎬 يوتيوب | تويتر | Kwai

✨ الميزة الجديدة: اختيار الجودة قبل التحميل
"""

URL_PATTERN = re.compile(r'https?://\S+')
# نخزن روابط المستخدمين مؤقتاً
user_last_url = {}

def is_url(text):
    return bool(URL_PATTERN.search(text))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME, parse_mode='Markdown')

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    urls = URL_PATTERN.findall(text)
    if not urls:
        return
    url = urls[0]
    user_id = update.effective_user.id
    user_last_url[user_id] = url

    # نفحص الفيديو بسرعة بدون تحميل لنطلع العنوان
    try:
        def get_info():
            with yt_dlp.YoutubeDL({'quiet': True, 'noplaylist': True}) as ydl:
                return ydl.extract_info(url, download=False)
        info = await asyncio.to_thread(get_info)
        title = info.get('title', 'فيديو')[:60]
    except:
        title = "فيديو"

    keyboard = [
        [InlineKeyboardButton(f"🔥 أفضل جودة - {title[:20]}", callback_data="best")],
        [
            InlineKeyboardButton("🎬 720p HD", callback_data="720"),
            InlineKeyboardButton("📱 480p", callback_data="480"),
        ],
        [
            InlineKeyboardButton("📱 360p (حجم صغير)", callback_data="360"),
            InlineKeyboardButton("🎵 صوت MP3 فقط", callback_data="mp3"),
        ],
        [InlineKeyboardButton("❌ إلغاء", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"✅ وجدت الفيديو:\n**{title}**\n\n👇 اختار الجودة اللي تبيها:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data
    user_id = query.from_user.id

    if choice == "cancel":
        await query.edit_message_text("❌ تم الإلغاء")
        return

    url = user_last_url.get(user_id)
    if not url:
        await query.edit_message_text("❌ الرابط انتهى، أرسله مرة ثانية")
        return

    # خريطة الجودات
    format_map = {
        "best": 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        "720": 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]',
        "480": 'bestvideo[height<=480][ext=mp4]+bestaudio/best[height<=480][ext=mp4]/best[height<=480]',
        "360": 'bestvideo[height<=360][ext=mp4]+bestaudio/best[height<=360]',
        "mp3": 'bestaudio/best'
    }

    ydl_opts = {
        'format': format_map.get(choice, format_map['best']),
        'outtmpl': str(DOWNLOAD_DIR / '%(title)s.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
    }

    if choice == "mp3":
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]

    await query.edit_message_text(f"⏳ جاري تحميل بجودة **{choice}**...\nقد يأخذ 15-30 ثانية، لا ترسل شي ثاني", parse_mode='Markdown')

    file_path = None
    try:
        def download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                fname = ydl.prepare_filename(info)
                # لو mp3، الاسم يتغير
                if choice == "mp3":
                    p = Path(fname)
                    # yt-dlp يحولها لـ mp3
                    possible = list(DOWNLOAD_DIR.glob(f"{p.stem}.*"))
                    if possible:
                        return str(possible[0]), info
                return fname, info

        file_path_str, info = await asyncio.to_thread(download)
        file_path = Path(file_path_str)
        # في حالة mp3 قد يكون الاسم مختلف
        if not file_path.exists():
            # دور على أحدث ملف
            files = sorted(DOWNLOAD_DIR.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True)
            if files:
                file_path = files[0]

        caption = f"🎬 {info.get('title','')[:100]}\n💎 الجودة: {choice}\n\n🤖 @Coin_YE_Bot"

        if choice == "mp3":
            await context.bot.send_audio(chat_id=query.message.chat_id, audio=open(file_path, 'rb'), caption=caption)
        else:
            await context.bot.send_video(chat_id=query.message.chat_id, video=open(file_path, 'rb'), caption=caption, supports_streaming=True)

        await query.delete_message()

    except Exception as e:
        await query.edit_message_text(f"❌ فشل: {str(e)[:400]}")
    finally:
        if file_path and file_path.exists():
            try:
                file_path.unlink()
            except:
                pass
        user_last_url.pop(user_id, None)

def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN not set")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(button_callback))
    print("🚀 V2 Bot with Quality Selection Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
