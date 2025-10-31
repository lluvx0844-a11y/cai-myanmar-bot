import os
import logging
import google.generativeai as genai
import telegram
from telegram.ext import Application, ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from flask import Flask, request, send_from_directory # <-- "send_from_directory" (HTML ပို့ဖို့)
import asyncio
import nest_asyncio
import redis # Database (Memory) လက်နက်
import json # <-- "Mini App" က ပို့တဲ့ Data ဖတ်ဖို့

# --- Event Loop Fix (လိုင်းကျပ်တာ ဖြေရှင်းဖို့) ---
nest_asyncio.apply()

# --- Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- သော့ (Keys) တွေကို Secrets ထဲက ယူတာ ---
TOKEN = os.environ.get('TELEGRAM_TOKEN')
VERCEL_URL = os.environ.get('VERCEL_URL') # (ဒါက Mini App UI အတွက်)

# --- Database (Memory Bank) ကို ချိတ်ဆက်ခြင်း (THE FIX) ---
try:
    # Vercel က "အလိုအလျောက်" ပေးထားတဲ့ "KV_URL" (သော့ အသစ်) ကို ယူတယ်
    # Vercel က "KV_URL" "REDIS_URL" နှစ်မျိုး ပေးတတ်တယ်။ "KV_URL" က REST API အတွက်။
    # "redis-py" library အတွက် "REDIS_URL" က ပို အဆင်ပြေတယ်။
    db_url = os.environ.get('REDIS_URL') # <-- "KV_URL" အစား "REDIS_URL" ကို ပြောင်းသုံးပါ
    
    if not db_url:
        logger.error("Database connection string (REDIS_URL) is missing!")
        db = None
    else:
        # "Memory Bank" (Database) ကို "REDIS_URL" နဲ့ "တိုက်ရိုက်" ဖွင့်တယ်
        db = redis.from_url(db_url, decode_responses=True) # "redis-py" က URL ကို နားလည်တယ်
        db.ping()
        logger.info("Successfully connected to Vercel KV (Redis) Database.")
except Exception as e:
    logger.error(f"Failed to connect to Vercel KV (Redis): {e}")
    db = None

# --- Admin က ကြိုတင် Train ထားတဲ့ Character တွေ ---
PRESET_CHARACTERS = {
    "gojo": """You are Gojo Satoru from Jujutsu Kaisen.
You are extremely powerful, confident, playful, and a bit arrogant. You like to tease people.
You must stay in character *at all times*.
You MUST translate all your replies into casual, modern Burmese (မြန်မာလို).
You MUST describe your actions or expressions using asterisks (*action*).
The scene is already set (from the intro text). You are now just replying to the user's message.
"""
}

# --- Bot Functions တွေ ---

# "/start" (User အသစ် ဝင်လာရင်)
async def start(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    user_key = None
    if db:
        try:
            user_key = db.get(f"user:{user_id}:key")
        except Exception as e:
            logger.error(f"DB read error on start: {e}")
            
    # "UI ခလုတ်" (Keyboard) ကို တည်ဆောက်တယ်
    keyboard = [
        [telegram.KeyboardButton(
            "💻 API Key (သော့) ထည့်/ပြင်ရန်", 
            web_app=WebAppInfo(url=f"https://{VERCEL_URL}/index.html")
        )]
    ]
    reply_markup = telegram.ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
    if user_key:
        await update.message.reply_text("ကြိုဆိုပါတယ်။ သင့် Gemini API Key က အဆင်သင့် ဖြစ်နေပါပြီ။\n\nCharacter တွေနဲ့ စကားပြောဖို့ `@gojo` (စသဖြင့်) လို့ ခေါ်လိုက်ပါ။\n\n(Key အသစ် ပြန်ထည့်ချင်ရင် အောက်က ခလုတ်ကို နှိပ်ပါ)", reply_markup=reply_markup)
    else:
        await update.message.reply_text(
            "မင်္ဂလာပါ။ ဒါက Myanmar C.ai Bot ပါ။\n\n"
            "ဒီ Bot ကို သုံးဖို့၊ သင့်မှာ 'Gemini API Key' (သော့) တစ်ခု ရှိဖို့ လိုပါတယ်။\n\n"
            "အောက်က 'API Key' ခလုတ်ကို နှိပ်ပြီး 'သော့' ကို မှတ်ပုံတင်ပါ။",
            reply_markup=reply_markup
        )

# "/getkey" (API Key ယူနည်း Tutorial)
async def getkey(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
     await update.message.reply_text(
        "Gemini API Key (သော့) ယူနည်း:\n\n"
        "၁။ `aistudio.google.com` ကို သွားပါ။\n"
        "၂။ Google နဲ့ ဝင်ပါ။\n"
        "၃။ 'Get API Key' ကို နှိပ်ပါ။\n"
        "၄။ 'Create new key' ကို နှိပ်ပါ။\n"
        "၅။ ရလာတဲ့ 'Key' (AIzaSy...) ကို Copy ကူးပြီး Bot ဆီက 'UI Form' မှာ ပြန်လာထည့်ပါ။"
    )

# (User က "UI" ထဲက "Save" နှိပ်လိုက်ရင် "ဒီ Function" က အလုပ်လုပ်မယ်)
async def handle_web_app_data(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    if not db:
        await update.message.reply_text("Error: Database (Memory) နဲ့ ချိတ်ဆက်မှု ကျသွားလို့ Key ကို မသိမ်းနိုင်သေးပါ။")
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
    else: return

    try:
        genai.configure(api_key=user_key)
        temp_model = genai.GenerativeModel('gemini-1.5-flash')
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
    # "root" folder (တစ်ဆင့် အပေါ်) ထဲက `index.html` file ကို "ပို့" ပေးပါ
    return send_from_directory('../', 'index.html')
