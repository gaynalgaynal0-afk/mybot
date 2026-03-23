import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = "@jv60fps"
CHANNEL_LINK = "https://t.me/jv60fps"

bot = telebot.TeleBot(BOT_TOKEN)

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
    kb.add(InlineKeyboardButton("🔑 Get My API Key", callback_data="get_api"))
    bot.send_message(m.chat.id, f"👋 Welcome *{m.from_user.first_name}*!\n\n1️⃣ Join channel\n2️⃣ Click Get API Key\n3️⃣ Paste in extension\n\n⚠️ Key stops if you leave!", parse_mode="Markdown", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "get_api")
def button(c):
    uid = c.from_user.id
    bot.answer_callback_query(c.id)
    kb = InlineKeyboardMarkup()
    if is_member(uid):
        kb.add(InlineKeyboardButton("📢 Channel", url=CHANNEL_LINK))
        bot.edit_message_text(f"✅ *Verified!*\n\n🔑 *Your API Key:*\n`{uid}`\n\nPaste in extension!", c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=kb)
    else:
        kb.add(InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK))
        kb.add(InlineKeyboardButton("🔄 Try Again", callback_data="get_api"))
        bot.edit_message_text("❌ *Access Denied!*\n\nJoin our channel first!", c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=kb)

print("🤖 Bot is running!")
bot.infinity_polling()