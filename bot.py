import os
import json
import threading
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ── Config ──────────────────────────────────────────────────────────────────
BOT_TOKEN    = os.environ.get("BOT_TOKEN")
CHANNEL_ID   = os.environ.get("CHANNEL_ID", "@jv60fps")
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "https://t.me/jv60fps")
ADMIN_ID     = int(os.environ.get("ADMIN_ID", "0"))        # your Telegram user ID
ADMIN_PASS   = os.environ.get("ADMIN_PASSWORD", "admin123") # change this!
SECRET_KEY   = os.environ.get("SECRET_KEY", "supersecretkey123")
PORT         = int(os.environ.get("PORT", 8080))

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
app.secret_key = SECRET_KEY

# ── Simple in-memory DB (persists while bot is running) ───────────────────
db = {
    "users": {},       # uid → {name, username, joined_at, verified, api_calls}
    "blocked": set(),  # set of blocked user IDs
    "broadcast_log": [],
    "stats": {
        "total_starts": 0,
        "total_verifications": 0,
        "total_denied": 0,
    }
}

def save_user(user, verified=False):
    uid = str(user.id)
    if uid not in db["users"]:
        db["users"][uid] = {
            "id": user.id,
            "name": user.first_name + (" " + user.last_name if user.last_name else ""),
            "username": user.username or "N/A",
            "joined_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "verified": verified,
            "api_calls": 0,
        }
    if verified:
        db["users"][uid]["verified"] = True
        db["users"][uid]["api_calls"] = db["users"][uid].get("api_calls", 0) + 1


# ── Telegram Bot Handlers ────────────────────────────────────────────────────
def is_member(uid):
    try:
        m = bot.get_chat_member(CHANNEL_ID, uid)
        return m.status in ["member", "administrator", "creator"]
    except:
        return False

@bot.message_handler(commands=["start", "help"])
def start(m):
    if str(m.from_user.id) in db["blocked"]:
        bot.send_message(m.chat.id, "🚫 You have been blocked from using this bot.")
        return
    db["stats"]["total_starts"] += 1
    save_user(m.from_user)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK))
    kb.add(InlineKeyboardButton("🔑 Get My API Key", callback_data="get_api"))
    bot.send_message(
        m.chat.id,
        f"👋 Welcome *{m.from_user.first_name}*!\n\n"
        "1️⃣ Join channel\n2️⃣ Click Get API Key\n3️⃣ Paste in extension\n\n"
        "⚠️ Key stops if you leave!",
        parse_mode="Markdown",
        reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data == "get_api")
def button(c):
    uid = c.from_user.id
    bot.answer_callback_query(c.id)
    if str(uid) in db["blocked"]:
        bot.answer_callback_query(c.id, "🚫 You are blocked.", show_alert=True)
        return
    kb = InlineKeyboardMarkup()
    if is_member(uid):
        db["stats"]["total_verifications"] += 1
        save_user(c.from_user, verified=True)
        kb.add(InlineKeyboardButton("📢 Channel", url=CHANNEL_LINK))
        bot.edit_message_text(
            f"✅ *Verified!*\n\n🔑 *Your API Key:*\n`{uid}`\n\nPaste in extension!",
            c.message.chat.id, c.message.message_id,
            parse_mode="Markdown", reply_markup=kb
        )
    else:
        db["stats"]["total_denied"] += 1
        kb.add(InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK))
        kb.add(InlineKeyboardButton("🔄 Try Again", callback_data="get_api"))
        bot.edit_message_text(
            "❌ *Access Denied!*\n\nJoin our channel first!",
            c.message.chat.id, c.message.message_id,
            parse_mode="Markdown", reply_markup=kb
        )

# Admin /stats command inside Telegram
@bot.message_handler(commands=["stats"])
def tg_stats(m):
    if m.from_user.id != ADMIN_ID:
        return
    s = db["stats"]
    u = db["users"]
    bot.send_message(
        m.chat.id,
        f"📊 *Bot Stats*\n\n"
        f"👥 Total Users: `{len(u)}`\n"
        f"▶️ /start calls: `{s['total_starts']}`\n"
        f"✅ Verifications: `{s['total_verifications']}`\n"
        f"❌ Denied: `{s['total_denied']}`\n"
        f"🚫 Blocked: `{len(db['blocked'])}`",
        parse_mode="Markdown"
    )

# Admin /broadcast command
@bot.message_handler(commands=["broadcast"])
def tg_broadcast(m):
    if m.from_user.id != ADMIN_ID:
        return
    text = m.text.replace("/broadcast", "").strip()
    if not text:
        bot.send_message(m.chat.id, "Usage: /broadcast <message>")
        return
    sent = 0
    for uid, info in db["users"].items():
        try:
            bot.send_message(int(uid), f"📢 *Announcement*\n\n{text}", parse_mode="Markdown")
            sent += 1
        except:
            pass
    db["broadcast_log"].append({"text": text, "sent_to": sent, "time": datetime.now().strftime("%Y-%m-%d %H:%M")})
    bot.send_message(m.chat.id, f"✅ Broadcast sent to {sent} users.")


# ── Admin Panel HTML ─────────────────────────────────────────────────────────
ADMIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bot Admin Panel</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; }
  .sidebar { width: 220px; background: #1e293b; height: 100vh; position: fixed; padding: 24px 0; }
  .sidebar h2 { color: #38bdf8; padding: 0 20px 20px; font-size: 1.1rem; border-bottom: 1px solid #334155; }
  .sidebar a { display: block; padding: 12px 20px; color: #94a3b8; text-decoration: none; font-size: 0.9rem; }
  .sidebar a:hover, .sidebar a.active { background: #334155; color: #38bdf8; }
  .main { margin-left: 220px; padding: 30px; }
  .topbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 28px; }
  .topbar h1 { font-size: 1.4rem; }
  .logout { background: #ef4444; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; text-decoration: none; font-size: 0.85rem; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 32px; }
  .card { background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }
  .card .label { font-size: 0.8rem; color: #64748b; text-transform: uppercase; letter-spacing: .05em; }
  .card .value { font-size: 2rem; font-weight: 700; color: #38bdf8; margin-top: 6px; }
  table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 12px; overflow: hidden; }
  th { background: #334155; padding: 12px 16px; text-align: left; font-size: 0.8rem; text-transform: uppercase; color: #94a3b8; }
  td { padding: 11px 16px; border-top: 1px solid #334155; font-size: 0.88rem; }
  tr:hover td { background: #243347; }
  .badge { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }
  .badge.yes { background: #166534; color: #86efac; }
  .badge.no  { background: #7f1d1d; color: #fca5a5; }
  .badge.blocked { background: #7c2d12; color: #fdba74; }
  .section-title { font-size: 1rem; font-weight: 600; margin-bottom: 14px; color: #cbd5e1; }
  .action-btn { border: none; padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 0.8rem; font-weight: 600; }
  .btn-red   { background: #ef4444; color: white; }
  .btn-green { background: #22c55e; color: white; }
  textarea, input[type=text], input[type=password] {
    background: #0f172a; border: 1px solid #334155; color: #e2e8f0;
    border-radius: 8px; padding: 10px 14px; font-size: 0.9rem; width: 100%;
  }
  .broadcast-form { background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; margin-bottom: 24px; }
  .broadcast-form textarea { height: 90px; resize: vertical; margin: 10px 0; }
  .submit-btn { background: #2563eb; color: white; border: none; padding: 10px 22px; border-radius: 8px; cursor: pointer; font-weight: 600; }
  .login-box { max-width: 360px; margin: 100px auto; background: #1e293b; border-radius: 16px; padding: 36px; border: 1px solid #334155; }
  .login-box h2 { margin-bottom: 24px; color: #38bdf8; }
  .login-box input { margin-bottom: 14px; }
  .alert { background: #7f1d1d; color: #fca5a5; padding: 10px 14px; border-radius: 8px; margin-bottom: 14px; font-size: 0.88rem; }
  .flash { background: #14532d; color: #86efac; padding: 10px 14px; border-radius: 8px; margin-bottom: 16px; font-size: 0.88rem; }
  .log-item { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 12px 16px; margin-bottom: 10px; font-size: 0.88rem; }
  .log-time { color: #64748b; font-size: 0.78rem; }
</style>
</head>
<body>
{% if not session.get('admin') %}
  <div class="login-box">
    <h2>🤖 Bot Admin</h2>
    {% if error %}<div class="alert">{{ error }}</div>{% endif %}
    <form method="POST" action="/admin/login">
      <input type="password" name="password" placeholder="Admin Password" required>
      <br>
      <button class="submit-btn" style="width:100%;margin-top:4px">Login</button>
    </form>
  </div>
{% else %}
  <div class="sidebar">
    <h2>🤖 Bot Admin</h2>
    <a href="/admin" class="{{ 'active' if page=='dashboard' }}">📊 Dashboard</a>
    <a href="/admin/users" class="{{ 'active' if page=='users' }}">👥 Users</a>
    <a href="/admin/broadcast" class="{{ 'active' if page=='broadcast' }}">📢 Broadcast</a>
    <a href="/admin/logs" class="{{ 'active' if page=='logs' }}">📋 Broadcast Log</a>
  </div>
  <div class="main">
    <div class="topbar">
      <h1>
        {% if page=='dashboard' %}📊 Dashboard
        {% elif page=='users' %}👥 Users
        {% elif page=='broadcast' %}📢 Broadcast
        {% elif page=='logs' %}📋 Broadcast Log
        {% endif %}
      </h1>
      <a href="/admin/logout" class="logout">Logout</a>
    </div>

    {% if flash %}<div class="flash">{{ flash }}</div>{% endif %}

    {% if page == 'dashboard' %}
      <div class="cards">
        <div class="card"><div class="label">Total Users</div><div class="value">{{ stats.users }}</div></div>
        <div class="card"><div class="label">Verified</div><div class="value">{{ stats.verified }}</div></div>
        <div class="card"><div class="label">Blocked</div><div class="value">{{ stats.blocked }}</div></div>
        <div class="card"><div class="label">/start Calls</div><div class="value">{{ stats.starts }}</div></div>
        <div class="card"><div class="label">Verifications</div><div class="value">{{ stats.verifications }}</div></div>
        <div class="card"><div class="label">Denied</div><div class="value">{{ stats.denied }}</div></div>
      </div>

    {% elif page == 'users' %}
      <table>
        <thead><tr><th>ID</th><th>Name</th><th>Username</th><th>Joined</th><th>Verified</th><th>API Calls</th><th>Action</th></tr></thead>
        <tbody>
          {% for uid, u in users.items() %}
          <tr>
            <td>{{ uid }}</td>
            <td>{{ u.name }}</td>
            <td>@{{ u.username }}</td>
            <td>{{ u.joined_at }}</td>
            <td>
              {% if uid in blocked %}<span class="badge blocked">Blocked</span>
              {% elif u.verified %}<span class="badge yes">✔ Yes</span>
              {% else %}<span class="badge no">✘ No</span>{% endif %}
            </td>
            <td>{{ u.api_calls }}</td>
            <td>
              {% if uid in blocked %}
                <form method="POST" action="/admin/unblock/{{ uid }}" style="display:inline">
                  <button class="action-btn btn-green">Unblock</button>
                </form>
              {% else %}
                <form method="POST" action="/admin/block/{{ uid }}" style="display:inline">
                  <button class="action-btn btn-red">Block</button>
                </form>
              {% endif %}
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>

    {% elif page == 'broadcast' %}
      <div class="broadcast-form">
        <div class="section-title">Send message to all users</div>
        <form method="POST" action="/admin/broadcast">
          <textarea name="message" placeholder="Type your broadcast message here..."></textarea>
          <button class="submit-btn">📢 Send Broadcast</button>
        </form>
      </div>

    {% elif page == 'logs' %}
      {% if not logs %}
        <p style="color:#64748b">No broadcasts sent yet.</p>
      {% endif %}
      {% for log in logs|reverse %}
        <div class="log-item">
          <div class="log-time">{{ log.time }} — sent to {{ log.sent_to }} users</div>
          <div style="margin-top:6px">{{ log.text }}</div>
        </div>
      {% endfor %}
    {% endif %}

  </div>
{% endif %}
</body>
</html>
"""

def admin_context(page, flash="", error=""):
    s = db["stats"]
    return {
        "page": page,
        "flash": flash,
        "error": error,
        "stats": {
            "users": len(db["users"]),
            "verified": sum(1 for u in db["users"].values() if u["verified"]),
            "blocked": len(db["blocked"]),
            "starts": s["total_starts"],
            "verifications": s["total_verifications"],
            "denied": s["total_denied"],
        },
        "users": db["users"],
        "blocked": db["blocked"],
        "logs": db["broadcast_log"],
    }

# ── Flask Routes ─────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return "🤖 Bot is running! Go to <a href='/admin'>/admin</a> for the panel."

@app.route("/admin")
def admin_dashboard():
    return render_template_string(ADMIN_HTML, **admin_context("dashboard"))

@app.route("/admin/login", methods=["POST"])
def admin_login():
    if request.form.get("password") == ADMIN_PASS:
        session["admin"] = True
        return redirect("/admin")
    return render_template_string(ADMIN_HTML, **admin_context("dashboard", error="Wrong password!"))

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect("/admin")

@app.route("/admin/users")
def admin_users():
    if not session.get("admin"):
        return redirect("/admin")
    return render_template_string(ADMIN_HTML, **admin_context("users"))

@app.route("/admin/block/<uid>", methods=["POST"])
def admin_block(uid):
    if not session.get("admin"):
        return redirect("/admin")
    db["blocked"].add(uid)
    return render_template_string(ADMIN_HTML, **admin_context("users", flash=f"User {uid} blocked."))

@app.route("/admin/unblock/<uid>", methods=["POST"])
def admin_unblock(uid):
    if not session.get("admin"):
        return redirect("/admin")
    db["blocked"].discard(uid)
    return render_template_string(ADMIN_HTML, **admin_context("users", flash=f"User {uid} unblocked."))

@app.route("/admin/broadcast", methods=["GET", "POST"])
def admin_broadcast():
    if not session.get("admin"):
        return redirect("/admin")
    if request.method == "POST":
        text = request.form.get("message", "").strip()
        if text:
            sent = 0
            for uid in db["users"]:
                try:
                    bot.send_message(int(uid), f"📢 *Announcement*\n\n{text}", parse_mode="Markdown")
                    sent += 1
                except:
                    pass
            db["broadcast_log"].append({"text": text, "sent_to": sent, "time": datetime.now().strftime("%Y-%m-%d %H:%M")})
            return render_template_string(ADMIN_HTML, **admin_context("broadcast", flash=f"✅ Sent to {sent} users!"))
    return render_template_string(ADMIN_HTML, **admin_context("broadcast"))

@app.route("/admin/logs")
def admin_logs():
    if not session.get("admin"):
        return redirect("/admin")
    return render_template_string(ADMIN_HTML, **admin_context("logs"))

# Health check endpoint for Render
@app.route("/health")
def health():
    return jsonify({"status": "ok", "users": len(db["users"])}), 200


# ── Run both bot + web server ────────────────────────────────────────────────
def run_bot():
    print("🤖 Bot polling started...")
    bot.infinity_polling()

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    print(f"🌐 Web server starting on port {PORT}...")
    app.run(host="0.0.0.0", port=PORT)
