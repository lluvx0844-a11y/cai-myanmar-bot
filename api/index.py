import os
import logging
import google.generativeai as genai
import telegram
from telegram import Update, WebAppInfo # <-- "WebAppInfo" (UI ခေါ်ဖို့) ထပ်ထည့်တယ်
from telegram.ext import Application, ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from flask import Flask, request, send_from_directory # <-- "send_from_directory" (HTML ပို့ဖို့) ထပ်ထည့်တယ်
import asyncio
import nest_asyncio
import redis
import json # <-- "Mini App" က ပို့တဲ့ Data ဖတ်ဖို့

# --- Event Loop Fix ---
nest_asyncio.apply()

# --- Logging ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- သော့ (Keys) ---
TOKEN = os.environ.get('TELEGRAM_TOKEN')
VERCEL_URL = os.environ.get('VERCEL_URL') # <-- Vercel က "အလိုအလျောက်" ပေးတဲ့ "အိမ်လိပ်စာ"

# --- Database (Memory) ---
try:
    db_url = os.environ.get('KV_URL')
    if not db_url: logger.error("KV_URL is missing!"); db = None
    else:
        db = redis.from_url(db_url, decode_responses=True)
        db.ping()
        logger.info("Successfully connected to Vercel KV Database.")
except Exception as e:
    logger.error(f"Failed to connect to Vercel KV: {e}"); db = None

# --- Admin Characters ---
PRESET_CHARACTERS = { "gojo": "You are Gojo Satoru..." } # (Code ကို ရှင်းအောင် ခဏ ချုံ့ထားတယ်)

# --- Bot Functions ---

# "/start" (User အသစ်)
async def start(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    user_key = None
    if db: user_key = db.get(f"user:{user_id}:key")
    
    # "UI ခလုတ်" (Keyboard) ကို တည်ဆောက်တယ်
    keyboard = [
        [telegram.KeyboardButton(
            "💻 API Key (သော့) ထည့်/ပြင်ရန်", 
            # "index.html" (UI) ကို ဖွင့်ပေးမယ့် "Mini App" ခလုတ်
            web_app=WebAppInfo(url=f"https://{VERCEL_URL}/index.html")
        )]
    ]
    reply_markup = telegram.ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    if user_key:
        await update.message.reply_text(
            "ကြိုဆိုပါတယ်။ သင့် Gemini API Key က အဆင်သင့် ဖြစ်နေပါပြီ။\n"
            "Character တွေနဲ့ စကားပြောဖို့ `@gojo` လို့ ခေါ်လိုက်ပါ။",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "မင်္ဂလာပါ။ ဒါက Myanmar C.ai Bot ပါ။\n\n"
            "ဒီ Bot ကို သုံးဖို့၊ သင့်မှာ 'Gemini API Key' (သော့) တစ်ခု ရှိဖို့ လိုပါတယ်။\n"
            "အောက်က 'API Key' ခလုတ်ကို နှိပ်ပြီး 'သော့' ကို မှတ်ပုံတင်ပါ။",
            reply_markup=reply_markup # "ခလုတ်" ကိုပါ တစ်ခါတည်း ပို့တယ်
        )

# (User က "UI" ထဲက "Save" နှိပ်လိုက်ရင် "ဒီ Function" က အလုပ်လုပ်မယ်)
async def handle_web_app_data(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    if not db:
        await update.message.reply_text("Error: Database (Memory) နဲ့ ချိတ်ဆက်မှု ကျသွားလို့ Key ကို မသိမ်းနိုင်သေးပါ။")
        return
        
    try:
        # "UI" က ပို့လိုက်တဲ့ "API Key" (Data) ကို ယူတယ်
        user_key = update.message.web_app_data.data
        
        if not user_key or not user_key.startswith("AIzaSy"):
             await update.message.reply_text("Error: Key ထည့်သွင်းပုံ မှားနေပါတယ်။ 'AIzaSy' နဲ့ စရပါမယ်။")
             return

        # "Key" အသစ်ကို Database ထဲ "သိမ်း" လိုက်ပြီ
        db.set(f"user:{user_id}:key", user_key)
        await update.message.reply_text("အောင်မြင်ပါတယ်။ သင့်ရဲ့ Gemini API Key ကို မှတ်ပုံတင်ပြီးပါပြီ။\nအခု Character တွေနဲ့ စကားစပြောနိုင်ပါပြီ။")
    except Exception as e:
        await update.message.reply_text(f"Database Error: Key ကို မသိမ်းနိုင်ပါ။ {e}")


# (User က Character Bot တွေကို ခေါ်တဲ့ အဓိက Function)
async def handle_chat(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    user_message = update.message.text
    if not db:
        await update.message.reply_text("Error: Database (Memory) နဲ့ ချိတ်ဆက်မှု ကျသွားလို့ပါ။")
        return
    user_key = db.get(f"user:{user_id}:key")
    if not user_key:
        await update.message.reply_text("Error: သင် 'API Key' မထည့်ရသေးပါ။\nအောက်က 'API Key' ခလုတ်ကို နှိပ်ပြီး အရင် ထည့်သွင်းပါ။")
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
    else:
        return # Chatroom -> Ignore

    # 3. "Gemini" ကို "User ရဲ့ Key" နဲ့ "သွားခေါ်"
    try:
        genai.configure(api_key=user_key)
        temp_model = genai.GenerativeModel('gemini-2.5-flash') # 1.5-flash ကိုပဲ သုံးမယ်
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
        # (Message Type အသစ်: "UI" က Data ပို့တာကို လက်ခံဖို့)
        application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
        application.add_handler(MessageHandler(filters.Entity("mention"), handle_chat))

        try: loop = asyncio.get_running_loop()
        except RuntimeError: loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
        loop.run_until_complete(application.initialize())
    except Exception as e:
        logger.error(f"Failed to initialize Telegram Application: {e}")
        application = None
else:
    logger.error("Missing TOKEN, DB, or VERCEL_URL.")

# --- Vercel အတွက် Web Server (Flask App) ---
app = Flask(__name__)

# (Telegram က "POST" နဲ့ "ဘဲလ်တီး" မယ့် နေရာ)
@app.route('/', methods=['POST'])
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
    # "root" folder (သင့် project folder) ထဲက `index.html` file ကို "ပို့" ပေးပါ
    return send_from_directory('.', 'index.html')
    
