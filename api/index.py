import os
import logging
import google.generativeai as genai
import telegram
from telegram import Update, WebAppInfo
from telegram.ext import Application, ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
import asyncio
import nest_asyncio
import redis
import json
from flask import Flask, request, send_from_directory # <--- Flask "ပြန်ပါ" လာပါပြီ

# --- Event Loop Fix ---
nest_asyncio.apply()

# --- Logging ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- သော့ (Keys) ---
TOKEN = os.environ.get('TELEGRAM_TOKEN')
VERCEL_URL = os.environ.get('VERCEL_URL') 

# --- Database (Memory) ---
try:
    db_url = os.environ.get('REDIS_URL') 
    if not db_url: logger.error("REDIS_URL is missing!"); db = None
    else:
        db = redis.from_url(db_url, decode_responses=True)
        db.ping()
        logger.info("Successfully connected to Vercel KV (Redis) Database.")
except Exception as e:
    logger.error(f"Failed to connect to Vercel KV: {e}"); db = None

# --- Admin Characters ---
PRESET_CHARACTERS = {
    "gojo": """You are Gojo Satoru... (Prompt အရှည်ကြီး) ... You MUST translate to Burmese."""
}

# --- Bot Functions တွေ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    user_key = None
    if db: user_key = db.get(f"user:{user_id}:key")
    
    if not VERCEL_URL:
        await update.message.reply_text("System Error: VERCEL_URL is not set!")
        return
        
    keyboard = [[telegram.KeyboardButton("💻 API Key (သော့) ထည့်/ပြင်ရန်", web_app=WebAppInfo(url=f"https://{VERCEL_URL}/public/index.html"))]]
    reply_markup = telegram.ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
    if user_key:
        await update.message.reply_text("ကြိုဆိုပါတယ်။ သင့် Key အဆင်သင့် ဖြစ်နေပါပြီ။", reply_markup=reply_markup)
    else:
        await update.message.reply_text("မင်္ဂလာပါ။ Bot သုံးဖို့ 'API Key' ခလုတ်ကို နှိပ်ပြီး 'သော့' ကို မှတ်ပုံတင်ပါ။", reply_markup=reply_markup)

async def getkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
     await update.message.reply_text("Gemini API Key (သော့) ယူနည်း:\n\n၁။ aistudio.google.com ... (စသဖြင့်)")

async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    if not db:
        await update.message.reply_text("Error: Database (Memory) နဲ့ ချိတ်ဆက်မှု ကျသွားလို့ပါ။")
        return
    try:
        user_key = update.message.web_app_data.data
        if not user_key or not user_key.startswith("AIzaSy"):
             await update.message.reply_text("Error: Key ထည့်သွင်းပုံ မှားနေပါတယ်။ 'AIzaSy' နဲ့ စရပါမယ်။")
             return
        db.set(f"user:{user_id}:key", user_key)
        await update.message.reply_text("အောင်မြင်ပါတယ်။ သင့်ရဲ့ Gemini API Key ကို မှတ်ပုံတင်ပြီးပါပြီ။")
    except Exception as e:
        await update.message.reply_text(f"Database Error: Key ကို မသိမ်းနိုင်ပါ။ {e}")

async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    user_message = update.message.text
    if not db:
        await update.message.reply_text("Error: Database (Memory) နဲ့ ချိတ်ဆက်မှု ကျသွားလို့ပါ။")
        return
    user_key = db.get(f"user:{user_id}:key")
    if not user_key:
        await update.message.reply_text("Error: သင် 'API Key' မထည့်ရသေးပါ။")
        return
    
    character_prompt = None
    if user_message.startswith("@"):
        parts = user_message.split(maxsplit=1)
        char_name = parts[0][1:].lower()
        if char_name in PRESET_CHARACTERS:
             character_prompt = PRESET_CHARACTERS[char_name]
             user_message = parts[1] if len(parts) > 1 else ""
        else:
             await update.message.reply_text(f"Error: Character '{char_name}' ကို ရှာမတွေ့ပါ။")
             return
    else: return

    try:
        genai.configure(api_key=user_key)
        temp_model = genai.GenerativeModel('gemini-2.5-flash')
        full_prompt = character_prompt + "\n\nUser: " + user_message + "\nYou:"
        response = temp_model.generate_content(full_prompt)
        await update.message.reply_text(response.text)
    except Exception as e:
        logger.error(f"Gemini API Error for User {user_id}: {e}", exc_info=True)
        await update.message.reply_text(f"Gemini Error: {e}")

# --- "အိမ်" (Vercel) နဲ့ "Bot" ကို ချိတ်ဆက်ခြင်း ---
application = None
if TOKEN and db and VERCEL_URL:
    try:
        application = ApplicationBuilder().token(TOKEN).build()
        application.add_handler(CommandHandler('start', start))
        application.add_handler(CommandHandler('getkey', getkey))
        application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
        application.add_handler(MessageHandler(filters.Entity("mention"), handle_chat))
        
        loop = asyncio.get_event_loop()
        loop.run_until_complete(application.initialize())
    except Exception as e:
        logger.error(f"Failed to initialize Telegram Application: {e}")
        application = None
else:
    logger.error("Missing TOKEN, DB, or VERCEL_URL.")

# --- Vercel အတွက် Web Server (Flask App) ---
app = Flask(__name__)

# (Telegram က "POST" နဲ့ "ဘဲလ်တီး" မယ့် နေရာ)
# (Webhook လိပ်စာက ".../api/index" ဖြစ်ရပါမယ်)
@app.route('/api/index', methods=['POST'])
def webhook():
    if not application: return 'Error: Bot not initialized', 500
    try:
        update = telegram.Update.de_json(request.get_json(force=True), application.bot)
        
        try: loop = asyncio.get_running_loop()
        except RuntimeError: loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
            
        loop.run_until_complete(application.process_update(update))
        return 'OK', 200
    except Exception as e:
        logger.error(f"Webhook Error: {e}", exc_info=True)
        return 'Error', 500

# (User က "UI" (`index.html`) ကို "GET" နဲ့ "လာတောင်း" မယ့် နေရာ)
@app.route('/index.html')
def get_html_ui():
    # "public" folder (တစ်ဆင့် အပေါ်) ထဲက `index.html` file ကို "ပို့" ပေးပါ
    return send_from_directory('../public', 'index.html')
            
