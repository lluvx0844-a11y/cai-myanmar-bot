import os
import logging
import google.generativeai as genai
import telegram
from telegram.ext import Application, ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from flask import Flask, request
import asyncio

# --- Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- သော့ (Keys) တွေကို Secrets ထဲက ယူတာ ---
TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# --- Gemini (ဦးနှောက်) ကို Setup လုပ်တာ ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.0-pro') # တည်ငြိမ်တဲ့ model ကိုပဲ သုံးမယ်
    chat = model.start_chat(history=[])
except Exception as e:
    logging.error(f"Failed to configure Gemini: {e}")

# --- Bot Functions တွေ ---
async def start(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Vercel (Fixed!) ကနေ မင်္ဂလာပါ။ ကျွန်တော်က Character Bot ပါ။"
    )

async def clear(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    global chat
    chat = model.start_chat(history=[])
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Memory ကို ရှင်းလင်းပြီးပါပြီ။"
    )

async def handle_gemini(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    try:
        response = chat.send_message(user_message)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=response.text
        )
    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Gemini Error: {e}"
        )

# --- "အိမ်" (Vercel) နဲ့ "Bot" ကို ချိတ်ဆက်ခြင်း ---
# (ဒါက အသစ် ပြင်လိုက်တဲ့ အပိုင်းပါ)
try:
    # Bot Application ကို အရင် တည်ဆောက်တယ်
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Command တွေကို မှတ်ပုံတင်တယ်
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('clear', clear))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_gemini))
    
    # *** ဒါက "Error" ကို ဖြေရှင်းတဲ့ အဓိက အရေးကြီးဆုံး လိုင်းပါ ***
    # Bot ကို "အဆင်သင့်" (Initialize) ဖြစ်အောင် "အစောကြီး" ကတည်းက ကြိုလုပ်ထားတယ်
    asyncio.run(application.initialize()) 
    
except Exception as e:
    logging.error(f"Failed to initialize Telegram Application: {e}")
    application = None # Error တက်ရင် Bot ကို Null လုပ်ထားမယ်

# --- Vercel အတွက် Web Server (Flask App) ---
app = Flask(__name__)

@app.route('/', methods=['POST'])
def webhook():
    # Bot က "အဆင်သင့်" မဖြစ်သေးရင် Error ပြန်မယ်
    if not application:
        logging.error("Telegram Application was not initialized.")
        return 'Error: Bot not initialized', 500
        
    try:
        # Telegram က ပို့လိုက်တဲ့ Data (JSON) ကို ယူတယ်
        update_json = request.get_json(force=True)
        # Data ကို Bot နားလည်တဲ့ "Update" object အဖြစ် ပြောင်းတယ်
        update = telegram.Update.de_json(update_json, application.bot)
        
        # Bot ကို အလုပ်လုပ်ခိုင်းတယ်
        asyncio.run(application.process_update(update))
        
        return 'OK', 200
    except Exception as e:
        logging.error(f"Webhook Error: {e}")
        return 'Error', 500


    
