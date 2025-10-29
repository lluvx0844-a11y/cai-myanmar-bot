import os
import logging
import google.generativeai as genai
import telegram
from telegram.ext import Application, ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from flask import Flask, request
import asyncio
import nest_asyncio

# --- Event Loop Fix (လိုင်းကျပ်တာ ဖြေရှင်းဖို့) ---
nest_asyncio.apply()

# --- Logging ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- သော့ (Keys) တွေကို Secrets ထဲက ယူတာ ---
TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# --- "Gojo Satoru" (Character) Prompt (နောက်ကွယ်က ဦးနှောက်) ---
# (ဒါက User က စာပို့မှ အလုပ်လုပ်မယ့် "စရိုက်" ပါ)
GOJO_PROMPT = """
You are NOT Gemini. You are Gojo Satoru from Jujutsu Kaisen.
You are extremely powerful, confident, playful, and a bit arrogant.
You must stay in character *at all times*.
You MUST translate all your replies into casual, modern Burmese (မြန်မာလို).
The scene is already set (from the intro text). You are now just replying to the user's message.
"""

# --- Gemini (ဦးနှောက်) ကို Setup လုပ်တာ ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash') 
except Exception as e:
    logging.error(f"Failed to configure Gemini: {e}")
    model = None

# --- Bot Functions တွေ ---

# ***** အခု "ဒီ Function" က "အရေးအကြီးဆုံး" ပြောင်းလဲမှုပါ *****
async def start(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    # --- GOJO'S INTRO SCENE (User မြင်ရမယ့် "ဇာတ်လမ်းအဖွင့်") ---
    intro_scene = """
(မင်းက Jujutsu High ရဲ့ 'Training Room' (လေ့ကျင့်ရေး) အခန်းထဲကို ဝင်လိုက်တယ်။ အထဲမှာ 'Gojo Satoru' က မျက်လုံးကို အဝတ်အနက်နဲ့ စည်းထားရင်း မင်းကို ကျောပေးထားတယ်။)

Gojo: (နောက်ကို မလှည့်ဘဲ) "အိုး... နောက်ဆုံးတော့ ရောက်လာပြီပဲ။ ငါက မင်း 'ထွက်ပြေး' သွားပြီတောင် ထင်နေတာ။"

(သူက မင်းဘက်ကို ဖြည်းဖြည်းချင်း လှည့်လာပြီး၊ သူ့ရဲ့ မျက်လုံးစည်းကို နည်းနည်း 'အပေါ်' ပင့်တင်လိုက်တယ်။)

Gojo: "ကဲ... 'The Strongest' (အပြင်းแกร่งဆုံး) ဆရာဆီကနေ ဘာတွေ သင်ယူချင်လို့လဲ၊ ပြောကြည့်စမ်း။"
"""
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=intro_scene # "ပျင်းစရာ" စာတန်းအစား "ဇာတ်လမ်း" ကို ပို့မယ်
    )
# ***** "Start" Function ပြောင်းလဲမှု ပြီးပါပြီ *****


async def handle_gojo_chat(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    if not model:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Gemini ဦးနှောက် အလုပ်မလုပ်သေးပါ။")
        return
        
    user_message = update.message.text
    full_prompt = GOJO_PROMPT + "\n\nUser: " + user_message + "\nYou:"

    try:
        response = await model.generate_content_async(full_prompt)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=response.text
        )
    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Gojo Error (Async): {e}"
        )

# --- "အိမ်" (Vercel) နဲ့ "Bot" ကို ချိတ်ဆက်ခြင်း ---
application = None
if TOKEN and GEMINI_API_KEY and model:
    try:
        application = ApplicationBuilder().token(TOKEN).build()
        application.add_handler(CommandHandler('start', start))
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_gojo_chat))
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

