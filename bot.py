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



# ── Animated Emojis ───────────────────────────────────────────────────────────
def _ae(eid, fb): return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'
E_MEGA  = _ae('5406719108123209742', '📢')  # 📢
E_KEY   = _ae('5274195706066781810', '🔑')  # 🔑
E_RESET = _ae('5195033767969839232', '🔄')  # 🔄
E_BAND  = _ae('5231102735817918643', '🩹')  # 🩹
E_GLOBE = _ae('5231102735817918643', '🌐')  # 🌐
E_GEAR  = _ae('5406802533567994492', '⚙️') # ⚙️
E_LOCK  = _ae('5429392313493242588', '🔐')  # 🔐
E_CHECK = _ae('5411197345968701560', '✅')       # ✅
E_CROSS = _ae('5406802533567994492', '❌')       # ❌
E_BLOCK = _ae('5289722755871162900', '🚫')  # 🚫
E_WAVE  = _ae('5406719108123209742', '👋')  # 👋
E_WARN  = _ae('5289722755871162900', '⚠️') # ⚠️
E_ONE   = _ae('5406719108123209742', '1️⃣')
E_TWO   = _ae('5195033767969839232', '2️⃣')
E_THREE = _ae('5411197345968701560', '3️⃣')
E_CHART = _ae('5274195706066781810', '📊')  # 📊
E_USERS = _ae('5429392313493242588', '👥')  # 👥
E_SRCH  = _ae('5274195706066781810', '🔍')  # 🔍
E_HOME  = _ae('5195033767969839232', '🏠')  # 🏠
E_ANNC  = _ae('5406719108123209742', '📢')  # 📢

# ── Helper: Main Menu Keyboard ────────────────────────────────────────────────
def main_menu_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(f"{E_MEGA} Join Channel", url=CHANNEL_LINK))
    kb.add(InlineKeyboardButton(f"{E_KEY} Get ID", callback_data="get_api"))
    kb.add(InlineKeyboardButton(f"{E_RESET} Reset Extension", callback_data="reset_key"))
    kb.row(
        InlineKeyboardButton(f"{E_BAND} Patcher", url="https://restless-star-a7e9.gaynalgaynal4.workers.dev/"),
        InlineKeyboardButton(f"{E_GLOBE} Website", url="https://frosty-paper-10d1.gaynalgaynal4.workers.dev/")
    )
    kb.add(InlineKeyboardButton(f"{E_GEAR} Methods", url="https://t.me/Nnotifyy_bot"))
    kb.add(InlineKeyboardButton(f"{E_LOCK} New Extension Password", callback_data="show_password"))
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
        bot.send_message(m.chat.id, f"{E_BLOCK} You have been blocked from using this service.")
        return
    bot.send_message(
        m.chat.id,
        f"{E_WAVE} Welcome <b>{m.from_user.first_name}</b>!\n\n{E_ONE} Join channel\n{E_TWO} Click Get ID\n{E_THREE} Paste in extension\n\n{E_WARN} Key stops if you leave!",
        parse_mode="HTML", reply_markup=main_menu_kb()
    )

@bot.callback_query_handler(func=lambda c: c.data == "get_api")
def button(c):
    uid = c.from_user.id
    bot.answer_callback_query(c.id)
    if str(uid) in db["blocked"]:
        bot.answer_callback_query(c.id, f"{E_BLOCK} You are blocked.", show_alert=True)
        return
    kb = InlineKeyboardMarkup()
    if is_member(uid):
        save_user(c.from_user, verified=True)
        kb.add(InlineKeyboardButton(f"{E_MEGA} Channel", url=CHANNEL_LINK))
        kb.add(InlineKeyboardButton(f"{E_HOME} Menu", callback_data="main_menu"))
        bot.edit_message_text(
            f"{E_CHECK} <b>Verified!</b>\n\n{E_KEY} <b>Your ID:</b>\n<code>7082829394</code>\n\nPaste in extension!",
            c.message.chat.id, c.message.message_id,
            parse_mode="HTML", reply_markup=kb
        )
    else:
        db["stats"]["total_denied"] += 1
        kb.add(InlineKeyboardButton(f"{E_MEGA} Join Channel", url=CHANNEL_LINK))
        kb.add(InlineKeyboardButton(f"{E_RESET} Try Again", callback_data="get_api"))
        kb.add(InlineKeyboardButton(f"{E_HOME} Menu", callback_data="main_menu"))
        bot.edit_message_text(
            f"{E_CROSS} <b>Access Denied!</b>\n\nJoin our channel first!",
            c.message.chat.id, c.message.message_id,
            parse_mode="HTML", reply_markup=kb
        )

@bot.callback_query_handler(func=lambda c: c.data == "reset_key")
def reset_key(c):
    uid = str(c.from_user.id)
    bot.answer_callback_query(c.id)
    if uid in db["blocked"]:
        bot.answer_callback_query(c.id, f"{E_BLOCK} You are blocked.", show_alert=True)
        return
    if uid in db["users"]:
        db["users"][uid]["active_token"] = None
        db["users"][uid]["verified"] = False
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(f"{E_KEY} Get ID", callback_data="get_api"))
    kb.add(InlineKeyboardButton(f"{E_MEGA} Channel", url=CHANNEL_LINK))
    kb.add(InlineKeyboardButton(f"{E_HOME} Menu", callback_data="main_menu"))
    bot.edit_message_text(
        f"{E_RESET} <b>Reset Extension!</b>\n\n{E_CHECK} You can use the extension now.\nClick below to claim the key on your new browser.",
        c.message.chat.id, c.message.message_id,
        parse_mode="HTML", reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data == "show_password")
def show_password(c):
    bot.answer_callback_query(c.id)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(f"{E_HOME} Menu", callback_data="main_menu"))
    bot.edit_message_text(
        f"{E_LOCK} <b>Extension Password</b>\n\n<code>7082829394</code>\n\nCopy and paste it in the extension!",
        c.message.chat.id, c.message.message_id,
        parse_mode="HTML", reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data == "main_menu")
def back_to_menu(c):
    bot.answer_callback_query(c.id)
    bot.edit_message_text(
        f"{E_WAVE} Welcome <b>{c.from_user.first_name}</b>!\n\n{E_ONE} Join channel\n{E_TWO} Click Get ID\n{E_THREE} Paste in extension\n\n{E_WARN} Key stops if you leave!",
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
        f"{E_CHART} <b>Bot Stats</b>\n\n{E_USERS} Total Users: <code>{len(db['users'])}</code>\n{E_CHECK} Verifications: <code>{s['total_verifications']}</code>\n{E_SRCH} Verify API Calls: <code>{s['total_verify_calls']}</code>\n{E_CROSS} Denied: <code>{s['total_denied']}</code>\n{E_BLOCK} Blocked: <code>{len(db['blocked'])}</code>",
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
            bot.send_message(int(uid), f"{E_ANNC} <b>Announcement</b>\n\n{text}", parse_mode="HTML")
            sent += 1
        except:
            pass
    db["broadcast_log"].append({"text": text, "sent_to": sent, "time": datetime.now().strftime("%Y-%m-%d %H:%M")})
    bot.send_message(m.chat.id, f"{E_CHECK} Broadcast sent to {sent} users.")


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
