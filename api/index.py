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
    # Model ကို "gemini-1.0-pro" (တည်ငြိမ်တဲ့) model ကိုပဲ သုံးမယ်
    model = genai.GenerativeModel('gemini-2.5-flash') 
    chat = model.start_chat(history=[])
except Exception as e:
    logging.error(f"Failed to configure Gemini: {e}")
    model = None
    chat = None

# --- Bot Functions တွေ ---
async def start(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Vercel (Final Fix!) ကနေ မင်္ဂလာပါ။ ကျွန်တော်က Character Bot ပါ။"
    )

async def clear(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    global chat
    if model:
        chat = model.start_chat(history=[])
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Memory ကို ရှင်းလင်းပြီးပါပြီ။"
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Gemini ဦးနှောက် အလုပ်မလုပ်သေးပါ။"
        )

async def handle_gemini(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    # Gemini အဆင်သင့် မဖြစ်သေးရင် User ကို အကြောင်းကြား
    if not chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Gemini Error: Bot is not correctly configured (Gemini model failed to load)."
        )
        return
        
    user_message = update.message.text
    try:
        # *** Error ဖြေရှင်းပြီးသား Code (Event Loop Fix) ***
        # Gemini API ကို "async" (Walkie-Talkie) နည်းနဲ့ ခေါ်တယ်
        response = await chat.send_message_async(user_message)
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=response.text
        )
    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Gemini Error (Async): {e}"
        )

# --- "အိမ်" (Vercel) နဲ့ "Bot" ကို ချိတ်ဆက်ခြင်း ---
# (Error ဖြေရှင်းပြီးသား Code)
application = None
if TOKEN and GEMINI_API_KEY and model:
    try:
        application = ApplicationBuilder().token(TOKEN).build()
        
        # Command တွေကို မှတ်ပုံတင်တယ်
        application.add_handler(CommandHandler('start', start))
        application.add_handler(CommandHandler('clear', clear))
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_gemini))
        
        # Bot ကို "အဆင်သင့်" (Initialize) ဖြစ်အောင် ကြိုလုပ်ထားတယ်
        asyncio.run(application.initialize())
        
    except Exception as e:
        logging.error(f"Failed to initialize Telegram Application: {e}")
        application = None
else:
    logging.error("Missing Environment Variables (TOKEN or API_KEY) or Gemini Model failed.")

# --- Vercel အတွက် Web Server (Flask App) ---
app = Flask(__name__)

@app.route('/', methods=['POST'])
def webhook():
    if not application:
        return 'Error: Bot not initialized', 500
        
    try:
        update = telegram.Update.de_json(request.get_json(force=True), application.bot)
        asyncio.run(application.process_update(update))
        return 'OK', 200
    except Exception as e:
        logging.error(f"Webhook Error: {e}")
        return 'Error', 500
            
