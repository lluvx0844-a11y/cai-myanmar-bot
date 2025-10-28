import os
import logging
import google.generativeai as genai
import telegram
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from flask import Flask, request

# --- သော့ (Keys) တွေကို Secrets ထဲက ယူတာ (ဒါကို Vercel မှာ သွားထည့်ရဦးမယ်) ---
TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# --- Gemini (ဦးနှောက်) ကို Setup လုပ်တာ ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.0-pro') # တည်ငြိမ်တဲ့ model ကိုပဲ သုံးမယ်
chat = model.start_chat(history=[])

# --- Bot Setup ---
bot = telegram.Bot(token=TOKEN)

# --- Command Functions ---
async def start(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Vercel ကနေ မင်္ဂလာပါ။ ကျွန်တော်က Character Bot ပါ။"
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

# --- Vercel အတွက် Web Server (Flask App) ---
app = Flask(__name__)

@app.route('/', methods=['POST'])
def webhook():
    try:
        # Telegram က ပို့လိုက်တဲ့ Data ကို ယူတယ်
        update = telegram.Update.de_json(request.get_json(force=True), bot)

        # Telegram Application ကို ခဏတာ တည်ဆောက်တယ်
        application = ApplicationBuilder().token(TOKEN).build()

        # Command တွေကို မှတ်ပုံတင်တယ်
        application.add_handler(CommandHandler('start', start))
        application.add_handler(CommandHandler('clear', clear))
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_gemini))

        # Bot ကို အလုပ်လုပ်ခိုင်းတယ်
        import asyncio
        asyncio.run(application.process_update(update))

        return 'OK', 200
    except Exception as e:
        logging.error(f"Webhook Error: {e}")
        return 'Error', 500

# (ဒီအောက်က main function က Vercel မှာ တကယ် အလုပ်မလုပ်ဘူး၊ ဒါပေမဲ့ testing အတွက် ထည့်ထားတာ)
if __name__ == '__main__':
    print("Starting Flask server for local testing...")
    app.run(debug=True)
    
