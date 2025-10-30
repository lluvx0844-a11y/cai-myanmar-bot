import os
import logging
import google.generativeai as genai
import telegram
from telegram.ext import Application, ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from flask import Flask, request
import asyncio
import nest_asyncio
import redis # Database (Memory) လက်နက်

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
# (Admin Gemini Key ကို Vercel မှာ ထည့်စရာမလိုတော့ဘူး)

# --- Database (Memory Bank) ကို ချိတ်ဆက်ခြင်း ---
try:
    # Vercel က "အလိုအလျောက်" ပေးထားတဲ့ KV (Redis) "သော့" တွေကို ယူတယ်
    db_url = os.environ.get('UPSTASH_REDIS_REST_URL')
    db_token = os.environ.get('UPSTASH_REDIS_REST_TOKEN')
    
    if not db_url or not db_token:
        logger.error("Database connection strings (UPSTASH) are missing!")
        db = None
    else:
        # "Memory Bank" (Database) ကို အဆင်သင့်ဖွင့်ထားတယ်
        db = redis.Redis(
            host=db_url.split('://')[1].split(':')[0], # Host ကို ခွဲထုတ်တယ်
            port=int(db_url.split(':')[-1]), # Port ကို ခွဲထုတ်တယ်
            password=db_token,
            ssl=True, # Vercel KV က SSL သုံးတယ်
            decode_responses=True # "Byte" တွေအစား "String" တွေ ပြန်ယူဖို့
        )
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
    # (ဒီနေရာမှာ "Sukuna" "Lana del Rey" စသဖြင့် "Prompt" တွေ ထပ်ထည့်လို့ရတယ်)
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
            
    if user_key:
        await update.message.reply_text("ကြိုဆိုပါတယ်။ သင့် Gemini API Key က အဆင်သင့် ဖြစ်နေပါပြီ။\n\nCharacter တွေနဲ့ စကားပြောဖို့ `@gojo` (စသဖြင့်) လို့ ခေါ်လိုက်ပါ။\n\n(Key အသစ် ပြန်ထည့်ချင်ရင် `/setkey [Key]` ကို သုံးပါ)")
    else:
        await update.message.reply_text(
            "မင်္ဂလာပါ။ ဒါက Myanmar C.ai Bot ပါ။\n\n"
            "ဒီ Bot ကို သုံးဖို့၊ သင့်မှာ 'Gemini API Key' (သော့) တစ်ခု ရှိဖို့ လိုပါတယ်။\n\n"
            "**'သော့' မရှိသေးရင်:** 'API Key' ကို (အခမဲ့) ဘယ်လို ယူရမလဲဆိုတဲ့ 'Tutorial' (နည်းလမ်း) ကို ကြည့်ဖို့ `/getkey` လို့ ရိုက်ထည့်ပါ။\n\n"
            "**'သော့' ရှိပြီးသားဆိုရင်:** `/setkey [သင့်ရဲ့ Key အရှည်ကြီး]` (ဥပမာ: `/setkey AIzaSy...`) လို့ ရိုက်ထည့်ပြီး 'သော့' ကို မှတ်ပုံတင်ပါ။"
        )

# "/getkey" (API Key ယူနည်း Tutorial)
async def getkey(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
     await update.message.reply_text(
        "Gemini API Key (သော့) ယူနည်း:\n\n"
        "၁။ `aistudio.google.com` ကို သွားပါ။\n"
        "၂။ Google နဲ့ ဝင်ပါ။\n"
        "၃။ 'Get API Key' ကို နှိပ်ပါ။\n"
        "၄။ 'Create new key' ကို နှိပ်ပါ။\n"
        "၅။ ရလာတဲ့ 'Key' (AIzaSy...) ကို Copy ကူးပြီး `/setkey [Key]` ဆိုပြီး ပြန်လာထည့်ပါ။"
    )

# "/setkey" (User က သူ့ Key ကို ထည့်သွင်းခြင်း)
async def setkey(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    if not db:
        await update.message.reply_text("Error: Database (Memory) နဲ့ ချိတ်ဆက်မှု ကျသွားလို့ Key ကို မသိမ်းနိုင်သေးပါ။")
        return
    try:
        user_key = " ".join(context.args)
        if not user_key or not user_key.startswith("AIzaSy"): # Gemini Key format
             await update.message.reply_text("Error: Key ထည့်သွင်းပုံ မှားနေပါတယ် ဒါမှမဟုတ် Gemini Key မဟုတ်ပါ။\nဥပမာ: `/setkey AIzaSy...`")
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

    # 1. User ရဲ့ "Key" ကို Database ထဲက "သွားရှာ"
    user_key = db.get(f"user:{user_id}:key")
    if not user_key:
        await update.message.reply_text("Error: သင် 'API Key' မထည့်ရသေးပါ။\n`/setkey [Key]` နဲ့ အရင် ထည့်သွင်းပါ။")
        return

    # 2. User က ဘယ် "Character" ကို ခေါ်တာလဲ "ရှာ"
    character_prompt = None
    if user_message.startswith("@"):
        parts = user_message.split(maxsplit=1)
        char_name = parts[0][1:].lower() # "@" ကို ဖြုတ်ပြီး lowercase ပြောင်း
        if char_name in PRESET_CHARACTERS:
             character_prompt = PRESET_CHARACTERS[char_name]
             user_message = parts[1] if len(parts) > 1 else "" # Message ကို ယူ
        else:
             # (နောက်မှ User ဖန်တီးထားတဲ့ Character တွေကို Database က ရှာမယ်)
             await update.message.reply_text(f"Error: Character '{char_name}' ကို ရှာမတွေ့ပါ။")
             return
    else:
        # "@" နဲ့ မခေါ်ရင် (Chatroom) -> Bot က "လျစ်လျူရှု" (Ignore) လုပ်
        return

    # 3. "Gemini" ကို "User ရဲ့ Key" နဲ့ "သွားခေါ်"
    try:
        # "User Key" နဲ့ "သီးသန့်" configure လုပ်တယ်
        genai.configure(api_key=user_key)
        temp_model = genai.GenerativeModel('gemini-1.0-pro')
        
        full_prompt = character_prompt + "\n\nUser: " + user_message + "\nYou:"
        response = temp_model.generate_content(full_prompt) # Use generate_content
        
        await update.message.reply_text(response.text)
        
    except Exception as e:
        # *** ဒါက "404 Error" ပြန်တက်လာမယ့် နေရာပါ ***
        logger.error(f"Gemini API Error for User {user_id}: {e}", exc_info=True)
        await update.message.reply_text(f"Gemini Error: {e}\n\n(သင့် API Key က ဒီ Model ကို သုံးခွင့် မရသေးတာ ဖြစ်နိုင်ပါတယ်။ Google AI Studio မှာ စစ်ဆေးပါ)")

# --- "အိမ်" (Vercel) နဲ့ "Bot" ကို ချိတ်ဆက်ခြင်း ---
application = None
if TOKEN and db:
    try:
        application = ApplicationBuilder().token(TOKEN).build()
        application.add_handler(CommandHandler('start', start))
        application.add_handler(CommandHandler('getkey', getkey))
        application.add_handler(CommandHandler('setkey', setkey))
        application.add_handler(MessageHandler(filters.Entity("mention"), handle_chat))

        try: loop = asyncio.get_running_loop()
        except RuntimeError: loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
        loop.run_until_complete(application.initialize())

    except Exception as e:
        logger.error(f"Failed to initialize Telegram Application: {e}")
        application = None
else:
    logger.error("Missing TOKEN or Database connection failed.")

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

