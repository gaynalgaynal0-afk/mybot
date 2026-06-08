import os
import threading
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, session, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ── Config ───────────────────────────────────────────────────────────────────
BOT_TOKEN    = os.environ.get("BOT_TOKEN")
CHANNEL_ID   = os.environ.get("CHANNEL_ID", "@jv60fps")
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "https://t.me/jv60fps")
ADMIN_ID     = int(os.environ.get("ADMIN_ID", "0"))
ADMIN_PASS   = os.environ.get("ADMIN_PASSWORD", "admin123")
SECRET_KEY   = os.environ.get("SECRET_KEY", "jvsecret999")
PORT         = int(os.environ.get("PORT", 8080))

bot = telebot.TeleBot(BOT_TOKEN, skip_pending=True)
app = Flask(__name__)
app.secret_key = SECRET_KEY

# ── Database ─────────────────────────────────────────────────────────────────
db = {
    "users": {},        # uid → info
    "blocked": set(),   # blocked uids (strings)
    "broadcast_log": [],
    "stats": {
        "total_starts": 0,
        "total_verifications": 0,
        "total_denied": 0,
        "total_verify_calls": 0,
    }
}

def save_user(user, verified=False):
    uid = str(user.id)
    if uid not in db["users"]:
        db["users"][uid] = {
            "id": user.id,
            "name": user.first_name + (" " + (user.last_name or "") if user.last_name else ""),
            "username": user.username or "N/A",
            "joined_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "verified": False,
            "active_token": None,
            "api_calls": 0,
            "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    if verified:
        db["users"][uid]["verified"] = True
        db["users"][uid]["api_calls"] += 1
        db["users"][uid]["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M")


# ── KEY API ENDPOINT — Extension calls this ───────────────────────────────────
@app.route("/verify/<uid>/<browser_token>")
def verify_user(uid, browser_token):
    db["stats"]["total_verify_calls"] += 1

    if uid in db["blocked"]:
        return jsonify({"allowed": False, "reason": "blocked"})

    try:
        m = bot.get_chat_member(CHANNEL_ID, int(uid))
        is_member = m.status in ["member", "administrator", "creator"]
    except:
        return jsonify({"allowed": False, "reason": "bot_error"})

    if not is_member:
        return jsonify({"allowed": False, "reason": "not_member"})

    user_data = db["users"].get(uid)
    stored_token = user_data["active_token"] if user_data else None

    if stored_token is None:
        if uid not in db["users"]:
            save_user(m.user)
        db["users"][uid]["active_token"] = browser_token
    elif stored_token != browser_token:
        return jsonify({"allowed": False, "reason": "session_taken"})

    try:
        user = m.user
        save_user(user, verified=True)
        db["stats"]["total_verifications"] += 1
        username = "@" + user.username if user.username else user.first_name
        return jsonify({"allowed": True, "username": username})
    except:
        return jsonify({"allowed": True, "username": "User"})


# ── Helper: Main Menu Keyboard ────────────────────────────────────────────────
def main_menu_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5406719108123209742">📢</tg-emoji> Join Channel", url=CHANNEL_LINK))
    kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5274195706066781810">🔑</tg-emoji> Get ID", callback_data="get_api"))
    kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5195033767969839232">🔄</tg-emoji> Reset Extension", callback_data="reset_key"))
    kb.row(
        InlineKeyboardButton("<tg-emoji emoji-id="5231102735817918643">🩹</tg-emoji> Patcher", url="https://restless-star-a7e9.gaynalgaynal4.workers.dev/"),
        InlineKeyboardButton("<tg-emoji emoji-id="5231102735817918643">🌐</tg-emoji> Website", url="https://frosty-paper-10d1.gaynalgaynal4.workers.dev/")
    )
    kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5406802533567994492">⚙️</tg-emoji> Methods", url="https://t.me/Nnotifyy_bot"))
    kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5429392313493242588">🔐</tg-emoji> New Extension Password", callback_data="show_password"))
    return kb


# ── Telegram Bot Handlers ─────────────────────────────────────────────────────
def is_member(uid):
    try:
        m = bot.get_chat_member(CHANNEL_ID, uid)
        return m.status in ["member", "administrator", "creator"]
    except:
        return False

@bot.message_handler(commands=["start", "help"])
def start(m):
    db["stats"]["total_starts"] += 1
    save_user(m.from_user)
    if str(m.from_user.id) in db["blocked"]:
        bot.send_message(m.chat.id, "<tg-emoji emoji-id="5289722755871162900">🚫</tg-emoji> You have been blocked from using this service.")
        return
    bot.send_message(
        m.chat.id,
        f"<tg-emoji emoji-id="5406719108123209742">👋</tg-emoji> Welcome <b>{m.from_user.first_name}</b>!\n\n"
        f"<tg-emoji emoji-id="5406719108123209742">1️⃣</tg-emoji> Join channel\n<tg-emoji emoji-id="5195033767969839232">2️⃣</tg-emoji> Click Get ID\n<tg-emoji emoji-id="5411197345968701560">3️⃣</tg-emoji> Paste in extension\n\n"
        f"<tg-emoji emoji-id="5289722755871162900">⚠️</tg-emoji> Key stops if you leave!",
        parse_mode="HTML", reply_markup=main_menu_kb()
    )

@bot.callback_query_handler(func=lambda c: c.data == "get_api")
def button(c):
    uid = c.from_user.id
    bot.answer_callback_query(c.id)
    if str(uid) in db["blocked"]:
        bot.answer_callback_query(c.id, "<tg-emoji emoji-id="5289722755871162900">🚫</tg-emoji> You are blocked.", show_alert=True)
        return
    kb = InlineKeyboardMarkup()
    if is_member(uid):
        save_user(c.from_user, verified=True)
        kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5406719108123209742">📢</tg-emoji> Channel", url=CHANNEL_LINK))
        kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5195033767969839232">🏠</tg-emoji> Menu", callback_data="main_menu"))
        bot.edit_message_text(
            f"<tg-emoji emoji-id="5411197345968701560">✅</tg-emoji> <b>Verified!</b>\n\n<tg-emoji emoji-id="5274195706066781810">🔑</tg-emoji> <b>Your ID:</b>\n<code>{7082829394}</code>\n\nPaste in extension!",
            c.message.chat.id, c.message.message_id,
            parse_mode="HTML", reply_markup=kb
        )
    else:
        db["stats"]["total_denied"] += 1
        kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5406719108123209742">📢</tg-emoji> Join Channel", url=CHANNEL_LINK))
        kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5195033767969839232">🔄</tg-emoji> Try Again", callback_data="get_api"))
        kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5195033767969839232">🏠</tg-emoji> Menu", callback_data="main_menu"))
        bot.edit_message_text(
            "<tg-emoji emoji-id="5406802533567994492">❌</tg-emoji> <b>Access Denied!</b>\n\nJoin our channel first!",
            c.message.chat.id, c.message.message_id,
            parse_mode="HTML", reply_markup=kb
        )

@bot.callback_query_handler(func=lambda c: c.data == "reset_key")
def reset_key(c):
    uid = str(c.from_user.id)
    bot.answer_callback_query(c.id)
    if uid in db["blocked"]:
        bot.answer_callback_query(c.id, "<tg-emoji emoji-id="5289722755871162900">🚫</tg-emoji> You are blocked.", show_alert=True)
        return
    if uid in db["users"]:
        db["users"][uid]["active_token"] = None
        db["users"][uid]["verified"] = False
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5274195706066781810">🔑</tg-emoji> Get ID", callback_data="get_api"))
    kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5406719108123209742">📢</tg-emoji> Channel", url=CHANNEL_LINK))
    kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5195033767969839232">🏠</tg-emoji> Menu", callback_data="main_menu"))
    bot.edit_message_text(
        "<tg-emoji emoji-id="5195033767969839232">🔄</tg-emoji> <b>Reset Extension!</b>\n\n"
        f"<tg-emoji emoji-id="5411197345968701560">✅</tg-emoji> You can use the extension now.\n"
        "Click below to claim the key on your new browser.",
        c.message.chat.id, c.message.message_id,
        parse_mode="HTML", reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data == "show_password")
def show_password(c):
    bot.answer_callback_query(c.id)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("<tg-emoji emoji-id="5195033767969839232">🏠</tg-emoji> Menu", callback_data="main_menu"))
    bot.edit_message_text(
        "<tg-emoji emoji-id="5429392313493242588">🔐</tg-emoji> <b>Extension Password</b>\n\n"
        "<code>7082829394</code>\n\n"
        "Copy and paste it in the extension!",
        c.message.chat.id, c.message.message_id,
        parse_mode="HTML", reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data == "main_menu")
def back_to_menu(c):
    bot.answer_callback_query(c.id)
    bot.edit_message_text(
        f"<tg-emoji emoji-id="5406719108123209742">👋</tg-emoji> Welcome <b>{c.from_user.first_name}</b>!\n\n"
        f"<tg-emoji emoji-id="5406719108123209742">1️⃣</tg-emoji> Join channel\n<tg-emoji emoji-id="5195033767969839232">2️⃣</tg-emoji> Click Get ID\n<tg-emoji emoji-id="5411197345968701560">3️⃣</tg-emoji> Paste in extension\n\n"
        f"<tg-emoji emoji-id="5289722755871162900">⚠️</tg-emoji> Key stops if you leave!",
        c.message.chat.id, c.message.message_id,
        parse_mode="HTML", reply_markup=main_menu_kb()
    )

@bot.message_handler(commands=["stats"])
def tg_stats(m):
    if m.from_user.id != ADMIN_ID:
        return
    s = db["stats"]
    bot.send_message(
        m.chat.id,
        f"<tg-emoji emoji-id="5274195706066781810">📊</tg-emoji> <b>Bot Stats</b>\n\n"
        f"<tg-emoji emoji-id="5429392313493242588">👥</tg-emoji> Total Users: <code>{len(db['users'])}</code>\n"
        f"<tg-emoji emoji-id="5411197345968701560">✅</tg-emoji> Verifications: <code>{s['total_verifications']}</code>\n"
        f"<tg-emoji emoji-id="5274195706066781810">🔍</tg-emoji> Verify API Calls: <code>{s['total_verify_calls']}</code>\n"
        f"<tg-emoji emoji-id="5406802533567994492">❌</tg-emoji> Denied: <code>{s['total_denied']}</code>\n"
        f"<tg-emoji emoji-id="5289722755871162900">🚫</tg-emoji> Blocked: <code>{len(db['blocked'])}</code>",
        parse_mode="HTML"
    )

@bot.message_handler(commands=["broadcast"])
def tg_broadcast(m):
    if m.from_user.id != ADMIN_ID:
        return
    text = m.text.replace("/broadcast", "").strip()
    if not text:
        bot.send_message(m.chat.id, "Usage: /broadcast <message>")
        return
    sent = 0
    for uid in db["users"]:
        try:
            bot.send_message(int(uid), f"<tg-emoji emoji-id="5406719108123209742">📢</tg-emoji> <b>Announcement</b>\n\n{text}", parse_mode="HTML")
            sent += 1
        except:
            pass
    db["broadcast_log"].append({"text": text, "sent_to": sent, "time": datetime.now().strftime("%Y-%m-%d %H:%M")})
    bot.send_message(m.chat.id, ff"<tg-emoji emoji-id="5411197345968701560">✅</tg-emoji> Broadcast sent to {sent} users.")


# ── Flask health check ────────────────────────────────────────────────────────
@app.route('/')
def home():
    return "Bot is running!"


# ── Run ───────────────────────────────────────────────────────────────────────
def run_bot():
    bot.remove_webhook()
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
