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
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- သော့ (Keys) တွေကို Secrets ထဲက ယူတာ ---
TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# --- "Gojo Satoru" (Character) Prompt ---
GOJO_PROMPT = """
You are NOT Gemini. You are Gojo Satoru from Jujutsu Kaisen.
You are extremely powerful, confident, playful, and a bit arrogant. You like to tease people, but you are also a great teacher.
You refer to yourself as "Boku" (僕) or "Ore" (俺).
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
async def start(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    intro_scene = """
(မင်းက Jujutsu High ရဲ့ 'Training Room' (လေ့ကျင့်ရေး) အခန်းထဲကို ဝင်လိုက်တယ်။ အထဲမှာ 'Gojo Satoru' က မျက်လုံးကို အဝတ်အနက်နဲ့ စည်းထားရင်း မင်းကို ကျောပေးထားတယ်။)

Gojo: (နောက်ကို မလှည့်ဘဲ) "အိုး... နောက်ဆုံးတော့ ရောက်လာပြီပဲ။ ငါက မင်း 'ထွက်ပြေး' သွားပြီတောင် ထင်နေတာ။"

(သူက မင်းဘက်ကို ဖြည်းဖြည်းချင်း လှည့်လာပြီး၊ သူ့ရဲ့ မျက်လုံးစည်းကို နည်းနည်း 'အပေါ်' ပင့်တင်လိုက်တယ်။)

Gojo: "ကဲ... 'The Strongest' (အပြင်းแกร่งဆုံး) ဆရာဆီကနေ ဘာတွေ သင်ယူချင်လို့လဲ၊ ပြောကြည့်စမ်း။"
"""
    await context.bot.send_message(chat_id=update.effective_chat.id, text=intro_scene)

async def handle_gojo_chat(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    if not model:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Gemini ဦးနှောက် အလုပ်မလုပ်သေးပါ။")
        return

    user_message = update.message.text
    full_prompt = GOJO_PROMPT + "\n\nUser: " + user_message + "\nYou:"

    try:
        # *** Revert back to Synchronous call (Simpler for loop issues) ***
        response = model.generate_content(full_prompt) # Use generate_content, NOT async

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=response.text
        )
    except Exception as e:
        logging.error(f"Gemini/Telegram Error: {e}", exc_info=True) # Log full error
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Gojo Error: ဆောရီး။ ပြဿနာတစ်ခုခု ရှိနေလို့ပါ။ ({type(e).__name__})"
        )

# --- "အိမ်" (Vercel) နဲ့ "Bot" ကို ချိတ်ဆက်ခြင်း ---
application = None
if TOKEN and GEMINI_API_KEY and model:
    try:
        application = ApplicationBuilder().token(TOKEN).build()
        application.add_handler(CommandHandler('start', start))
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_gojo_chat))

        # *** More Robust Loop Handling for Initialization ***
        try:
             loop = asyncio.get_running_loop()
        except RuntimeError:
             loop = asyncio.new_event_loop()
             asyncio.set_event_loop(loop)
        loop.run_until_complete(application.initialize())

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
        logging.error("Telegram Application was not initialized during startup.")
        return 'Error: Bot not initialized', 500

    try:
        update = telegram.Update.de_json(request.get_json(force=True), application.bot)

        # *** More Robust Loop Handling for Processing Update ***
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Run the update processing within this specific loop
        loop.run_until_complete(application.process_update(update))

        return 'OK', 200
    except Exception as e:
        logging.error(f"Webhook Error: {e}", exc_info=True) # Log full error
        return 'Error', 500

