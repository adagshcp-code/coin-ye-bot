from flask import Flask
from threading import Thread
import os

# --- حل مشكلة التعليق في Render (يفتح بورت وهمي) ---
app = Flask('')
@app.route('/')
def home():
    return "Bot is alive! @Coin_YE_Bot"
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
Thread(target=run_flask, daemon=True).start()
# --- نهاية الحل ---

import re
import asyncio
import logging
from pathlib import Path
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("BOT_TOKEN")
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# تخزين مؤقت للروابط
url_cache = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً بك في بوت التحميل!

"
        "أرسل رابط من يوتيوب، تيك توك، انستقرام، فيسبوك، تويتر ...
"
        "وسأعطيك خيارات الجودة للتحميل 🎬"
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not re.match(r'https?://', url):
        return
    
    msg = await update.message.reply_text("⏳ جاري فحص الرابط...")
    
    try:
        ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            title = info.get('title', 'video')[:50]
        
        # فلترة الجودات
        qualities = []
        seen = set()
        for f in formats:
            if f.get('vcodec') != 'none' and f.get('height'):
                h = f.get('height')
                if h not in seen and h >= 144:
                    seen.add(h)
                    qualities.append(h)
        qualities = sorted(list(seen), reverse=True)[:6]
        
        if not qualities:
            await msg.edit_text("❌ لم أجد جودات متاحة، سأحمل أفضل جودة...")
            # تحميل مباشر
            await download_video(update, context, url, 'best')
            return
        
        # حفظ الرابط
        url_cache[update.effective_user.id] = url
        
        keyboard = []
        for q in qualities:
            keyboard.append([InlineKeyboardButton(f"📹 {q}p", callback_data=f"q_{q}")])
        keyboard.append([InlineKeyboardButton("🔥 أفضل جودة", callback_data="q_best")])
        
        await msg.edit_text(
            f"🎬 {title}

اختر الجودة:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logging.error(e)
        await msg.edit_text(f"❌ خطأ: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    url = url_cache.get(user_id)
    
    if not url:
        await query.edit_message_text("❌ انتهت صلاحية الرابط، أرسله مرة أخرى")
        return
    
    quality = data.replace("q_", "")
    await query.edit_message_text(f"⏳ جاري التحميل بجودة {quality}...")
    
    try:
        await download_video_by_query(query, url, quality)
    except Exception as e:
        logging.error(e)
        await query.edit_message_text(f"❌ فشل التحميل: {e}")

async def download_video(update, context, url, quality):
    await update.message.reply_text("هذه الميزة قيد التشغيل...")
    
async def download_video_by_query(query, url, quality):
    # إعداد الجودة
    if quality == 'best':
        fmt = 'bestvideo+bestaudio/best'
    else:
        fmt = f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]'
    
    ydl_opts = {
        'format': fmt,
        'outtmpl': str(DOWNLOAD_DIR / '%(title)s.%(ext)s'),
        'merge_output_format': 'mp4',
    }
    
    loop = asyncio.get_event_loop()
    def dl():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, True)
            return ydl.prepare_filename(info)
    
    filepath = await loop.run_in_executor(None, dl)
    
    # إرسال الملف
    await query.message.reply_text("✅ تم التحميل، جاري الإرسال...")
    with open(filepath, 'rb') as f:
        await query.message.reply_video(video=f, caption=f"جودة {quality}")
    
    # حذف الملف بعد الإرسال
    try:
        os.remove(filepath)
    except:
        pass

def main():
    if not TOKEN:
        print("❌ BOT_TOKEN غير موجود!")
        return
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    application.add_handler(CallbackQueryHandler(button_handler))
    print("Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
