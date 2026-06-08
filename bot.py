import os
import threading
import telebot
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = "@jv_60fps"
CHANNEL_LINK = "https://t.me/jv_60fps"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def is_member(uid):
    try:
        m = bot.get_chat_member(CHANNEL_ID, uid)
        return m.status in ["member", "administrator", "creator"]
    except:
        return False

@bot.message_handler(commands=["start", "help"])
def start(m):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK))
    kb.add(InlineKeyboardButton("🔑 Get ID", callback_data="get_api"))
    bot.send_message(m.chat.id, f"👋 Welcome *{m.from_user.first_name}*!\n\n1️⃣ Join channel\n2️⃣ Click Get API Key\n3️⃣ Paste in extension\n\n⚠️ ID stops if you leave!", parse_mode="Markdown", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "get_api")
def button(c):
    uid = c.from_user.id
    bot.answer_callback_query(c.id)
    kb = InlineKeyboardMarkup()
    if is_member(uid):
        kb.add(InlineKeyboardButton("📢 Channel", url=CHANNEL_LINK))
        bot.edit_message_text(f"✅ *Verified!*\n\n🔑 *Your ID:*\n`{7082829394}`\n\nPaste in extension!", c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=kb)
    else:
        kb.add(InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK))
        kb.add(InlineKeyboardButton("🔄 Try Again", callback_data="get_api"))
        bot.edit_message_text("❌ *Access Denied!*\n\nJoin our channel first!", c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=kb)

def run_bot():
    bot.remove_webhook()
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
