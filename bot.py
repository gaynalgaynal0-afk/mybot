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
            "api_calls": 0,
            "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    if verified:
        db["users"][uid]["verified"] = True
        db["users"][uid]["api_calls"] += 1
        db["users"][uid]["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M")


# ── KEY API ENDPOINT — Extension calls this ───────────────────────────────────
@app.route("/verify/<uid>")
def verify_user(uid):
    """
    Extension calls: GET /verify/<telegram_user_id>
    Returns JSON: { "allowed": true/false, "reason": "..." }
    """
    db["stats"]["total_verify_calls"] += 1

    # 1. Blocked check — your admin panel controls this
    if uid in db["blocked"]:
        return jsonify({"allowed": False, "reason": "blocked"})

    # 2. Check Telegram channel membership
    try:
        m = bot.get_chat_member(CHANNEL_ID, int(uid))
        is_member = m.status in ["member", "administrator", "creator"]
    except:
        return jsonify({"allowed": False, "reason": "bot_error"})

    if not is_member:
        return jsonify({"allowed": False, "reason": "not_member"})

    # 3. Save user info
    try:
        user = m.user
        save_user(user, verified=True)
        db["stats"]["total_verifications"] += 1
        username = "@" + user.username if user.username else user.first_name
        return jsonify({"allowed": True, "username": username})
    except:
        return jsonify({"allowed": True, "username": "User"})


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
        bot.send_message(m.chat.id, "🚫 You have been blocked from using this service.")
        return
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK))
    kb.add(InlineKeyboardButton("🔑 Get My API Key", callback_data="get_api"))
    bot.send_message(
        m.chat.id,
        f"👋 Welcome *{m.from_user.first_name}*!\n\n"
        "1️⃣ Join channel\n2️⃣ Click Get API Key\n3️⃣ Paste in extension\n\n"
        "⚠️ Key stops if you leave!",
        parse_mode="Markdown", reply_markup=kb
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

@bot.message_handler(commands=["stats"])
def tg_stats(m):
    if m.from_user.id != ADMIN_ID:
        return
    s = db["stats"]
    bot.send_message(
        m.chat.id,
        f"📊 *Bot Stats*\n\n"
        f"👥 Total Users: `{len(db['users'])}`\n"
        f"✅ Verifications: `{s['total_verifications']}`\n"
        f"🔍 Verify API Calls: `{s['total_verify_calls']}`\n"
        f"❌ Denied: `{s['total_denied']}`\n"
        f"🚫 Blocked: `{len(db['blocked'])}`",
        parse_mode="Markdown"
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
            bot.send_message(int(uid), f"📢 *Announcement*\n\n{text}", parse_mode="Markdown")
            sent += 1
        except:
            pass
    db["broadcast_log"].append({"text": text, "sent_to": sent, "time": datetime.now().strftime("%Y-%m-%d %H:%M")})
    bot.send_message(m.chat.id, f"✅ Broadcast sent to {sent} users.")


# ── Admin Panel HTML ──────────────────────────────────────────────────────────
ADMIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JV-60FPS Admin</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; }
  .sidebar { width: 220px; background: #1e293b; height: 100vh; position: fixed; padding: 24px 0; }
  .sidebar h2 { color: #00e5ff; padding: 0 20px 20px; font-size: 1rem; border-bottom: 1px solid #334155; }
  .sidebar a { display: block; padding: 12px 20px; color: #94a3b8; text-decoration: none; font-size: 0.88rem; }
  .sidebar a:hover, .sidebar a.active { background: #334155; color: #00e5ff; }
  .main { margin-left: 220px; padding: 30px; }
  .topbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 28px; }
  .topbar h1 { font-size: 1.3rem; }
  .logout { background: #ef4444; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; text-decoration: none; font-size: 0.82rem; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 32px; }
  .card { background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }
  .card .label { font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: .05em; }
  .card .value { font-size: 2rem; font-weight: 700; color: #00e5ff; margin-top: 6px; }
  table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 12px; overflow: hidden; }
  th { background: #334155; padding: 12px 16px; text-align: left; font-size: 0.75rem; text-transform: uppercase; color: #94a3b8; }
  td { padding: 11px 16px; border-top: 1px solid #334155; font-size: 0.85rem; }
  tr:hover td { background: #243347; }
  .badge { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 0.72rem; font-weight: 700; }
  .badge.yes { background: #166534; color: #86efac; }
  .badge.no  { background: #7f1d1d; color: #fca5a5; }
  .badge.blocked { background: #7c2d12; color: #fdba74; }
  .action-btn { border: none; padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 0.78rem; font-weight: 700; }
  .btn-red   { background: #ef4444; color: white; }
  .btn-green { background: #22c55e; color: white; }
  textarea, input[type=text], input[type=password] {
    background: #0f172a; border: 1px solid #334155; color: #e2e8f0;
    border-radius: 8px; padding: 10px 14px; font-size: 0.88rem; width: 100%;
  }
  .section-box { background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; margin-bottom: 20px; }
  .section-box textarea { height: 90px; resize: vertical; margin: 10px 0; }
  .submit-btn { background: #2563eb; color: white; border: none; padding: 10px 22px; border-radius: 8px; cursor: pointer; font-weight: 700; }
  .login-box { max-width: 340px; margin: 100px auto; background: #1e293b; border-radius: 16px; padding: 36px; border: 1px solid #334155; }
  .login-box h2 { margin-bottom: 24px; color: #00e5ff; }
  .login-box input { margin-bottom: 14px; }
  .alert { background: #7f1d1d; color: #fca5a5; padding: 10px 14px; border-radius: 8px; margin-bottom: 14px; font-size: 0.85rem; }
  .flash { background: #14532d; color: #86efac; padding: 10px 14px; border-radius: 8px; margin-bottom: 16px; font-size: 0.85rem; }
  .log-item { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 12px 16px; margin-bottom: 10px; font-size: 0.85rem; }
  .log-time { color: #64748b; font-size: 0.75rem; }
  .verify-url { background: #0f172a; border: 1px solid #00e5ff33; border-radius: 8px; padding: 12px 16px; font-size: 0.8rem; color: #00e5ff; font-family: monospace; word-break: break-all; }
</style>
</head>
<body>
{% if not session.get('admin') %}
  <div class="login-box">
    <h2>🎮 JV-60FPS Admin</h2>
    {% if error %}<div class="alert">{{ error }}</div>{% endif %}
    <form method="POST" action="/admin/login">
      <input type="password" name="password" placeholder="Admin Password" required>
      <br>
      <button class="submit-btn" style="width:100%;margin-top:4px">Login</button>
    </form>
  </div>
{% else %}
  <div class="sidebar">
    <h2>🎮 JV-60FPS Admin</h2>
    <a href="/admin"            class="{{ 'active' if page=='dashboard' }}">📊 Dashboard</a>
    <a href="/admin/users"      class="{{ 'active' if page=='users' }}">👥 Users</a>
    <a href="/admin/broadcast"  class="{{ 'active' if page=='broadcast' }}">📢 Broadcast</a>
    <a href="/admin/logs"       class="{{ 'active' if page=='logs' }}">📋 Logs</a>
    <a href="/admin/settings"   class="{{ 'active' if page=='settings' }}">⚙️ Settings</a>
  </div>
  <div class="main">
    <div class="topbar">
      <h1>
        {% if page=='dashboard' %}📊 Dashboard
        {% elif page=='users' %}👥 Users
        {% elif page=='broadcast' %}📢 Broadcast
        {% elif page=='logs' %}📋 Broadcast Logs
        {% elif page=='settings' %}⚙️ Settings
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
        <div class="card"><div class="label">Verify API Calls</div><div class="value">{{ stats.verify_calls }}</div></div>
        <div class="card"><div class="label">Denied</div><div class="value">{{ stats.denied }}</div></div>
        <div class="card"><div class="label">/start Calls</div><div class="value">{{ stats.starts }}</div></div>
      </div>
      <div class="section-box">
        <div style="font-size:0.8rem;color:#64748b;margin-bottom:8px;">🔗 Extension Verify Endpoint (paste in popup.js)</div>
        <div class="verify-url">{{ verify_url }}</div>
      </div>

    {% elif page == 'users' %}
      <table>
        <thead><tr><th>ID</th><th>Name</th><th>Username</th><th>Joined</th><th>Last Seen</th><th>Status</th><th>Action</th></tr></thead>
        <tbody>
          {% for uid, u in users.items() %}
          <tr>
            <td>{{ uid }}</td>
            <td>{{ u.name }}</td>
            <td>@{{ u.username }}</td>
            <td>{{ u.joined_at }}</td>
            <td>{{ u.last_seen }}</td>
            <td>
              {% if uid in blocked %}<span class="badge blocked">🚫 Blocked</span>
              {% elif u.verified %}<span class="badge yes">✔ Active</span>
              {% else %}<span class="badge no">✘ Unverified</span>{% endif %}
            </td>
            <td>
              {% if uid in blocked %}
                <form method="POST" action="/admin/unblock/{{ uid }}" style="display:inline">
                  <button class="action-btn btn-green">✅ Unblock</button>
                </form>
              {% else %}
                <form method="POST" action="/admin/block/{{ uid }}" style="display:inline">
                  <button class="action-btn btn-red">🚫 Block</button>
                </form>
              {% endif %}
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>

    {% elif page == 'broadcast' %}
      <div class="section-box">
        <div style="font-size:0.9rem;font-weight:600;margin-bottom:8px;">Send message to all users</div>
        <form method="POST" action="/admin/broadcast">
          <textarea name="message" placeholder="Type your message..."></textarea>
          <button class="submit-btn">📢 Send Broadcast</button>
        </form>
      </div>

    {% elif page == 'logs' %}
      {% if not logs %}<p style="color:#64748b">No broadcasts yet.</p>{% endif %}
      {% for log in logs|reverse %}
        <div class="log-item">
          <div class="log-time">{{ log.time }} — sent to {{ log.sent_to }} users</div>
          <div style="margin-top:6px">{{ log.text }}</div>
        </div>
      {% endfor %}

    {% elif page == 'settings' %}
      <div class="section-box">
        <div style="font-size:0.9rem;font-weight:600;margin-bottom:12px;">🔗 Verify API URL</div>
        <p style="font-size:0.82rem;color:#94a3b8;margin-bottom:10px;">Copy this URL and paste it into your extension's <code>popup.js</code> as the VERIFY_URL.</p>
        <div class="verify-url">{{ verify_url }}</div>
      </div>
      <div class="section-box">
        <div style="font-size:0.9rem;font-weight:600;margin-bottom:12px;">🚫 Manually Block a User ID</div>
        <form method="POST" action="/admin/block-manual">
          <input type="text" name="uid" placeholder="Enter Telegram User ID to block" style="margin-bottom:10px">
          <button class="submit-btn btn-red" style="background:#ef4444">Block User</button>
        </form>
      </div>
      <div class="section-box">
        <div style="font-size:0.9rem;font-weight:600;margin-bottom:12px;">✅ Manually Unblock a User ID</div>
        <form method="POST" action="/admin/unblock-manual">
          <input type="text" name="uid" placeholder="Enter Telegram User ID to unblock" style="margin-bottom:10px">
          <button class="submit-btn">Unblock User</button>
        </form>
      </div>
    {% endif %}
  </div>
{% endif %}
</body>
</html>
"""

def ctx(page, flash="", error=""):
    s = db["stats"]
    host = request.host_url.rstrip("/")
    return {
        "page": page, "flash": flash, "error": error,
        "verify_url": f"{host}/verify/USER_ID",
        "stats": {
            "users": len(db["users"]),
            "verified": sum(1 for u in db["users"].values() if u["verified"]),
            "blocked": len(db["blocked"]),
            "starts": s["total_starts"],
            "verifications": s["total_verifications"],
            "denied": s["total_denied"],
            "verify_calls": s["total_verify_calls"],
        },
        "users": db["users"],
        "blocked": db["blocked"],
        "logs": db["broadcast_log"],
    }

# ── Flask Routes ──────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return '🤖 JV-60FPS Bot is running! <a href="/admin">Admin Panel</a>'

@app.route("/health")
def health():
    return jsonify({"status": "ok", "users": len(db["users"])}), 200

@app.route("/admin")
def admin():
    return render_template_string(ADMIN_HTML, **ctx("dashboard"))

@app.route("/admin/login", methods=["POST"])
def admin_login():
    if request.form.get("password") == ADMIN_PASS:
        session["admin"] = True
        return redirect("/admin")
    return render_template_string(ADMIN_HTML, **ctx("dashboard", error="Wrong password!"))

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect("/admin")

@app.route("/admin/users")
def admin_users():
    if not session.get("admin"): return redirect("/admin")
    return render_template_string(ADMIN_HTML, **ctx("users"))

@app.route("/admin/block/<uid>", methods=["POST"])
def admin_block(uid):
    if not session.get("admin"): return redirect("/admin")
    db["blocked"].add(uid)
    return render_template_string(ADMIN_HTML, **ctx("users", flash=f"🚫 User {uid} blocked. They can no longer use the extension."))

@app.route("/admin/unblock/<uid>", methods=["POST"])
def admin_unblock(uid):
    if not session.get("admin"): return redirect("/admin")
    db["blocked"].discard(uid)
    return render_template_string(ADMIN_HTML, **ctx("users", flash=f"✅ User {uid} unblocked."))

@app.route("/admin/block-manual", methods=["POST"])
def block_manual():
    if not session.get("admin"): return redirect("/admin")
    uid = request.form.get("uid", "").strip()
    if uid:
        db["blocked"].add(uid)
    return render_template_string(ADMIN_HTML, **ctx("settings", flash=f"🚫 User {uid} blocked."))

@app.route("/admin/unblock-manual", methods=["POST"])
def unblock_manual():
    if not session.get("admin"): return redirect("/admin")
    uid = request.form.get("uid", "").strip()
    db["blocked"].discard(uid)
    return render_template_string(ADMIN_HTML, **ctx("settings", flash=f"✅ User {uid} unblocked."))

@app.route("/admin/broadcast", methods=["GET", "POST"])
def admin_broadcast():
    if not session.get("admin"): return redirect("/admin")
    if request.method == "POST":
        text = request.form.get("message", "").strip()
        if text:
            sent = 0
            for uid in db["users"]:
                try:
                    bot.send_message(int(uid), f"📢 *Announcement*\n\n{text}", parse_mode="Markdown")
                    sent += 1
                except: pass
            db["broadcast_log"].append({"text": text, "sent_to": sent, "time": datetime.now().strftime("%Y-%m-%d %H:%M")})
            return render_template_string(ADMIN_HTML, **ctx("broadcast", flash=f"✅ Sent to {sent} users!"))
    return render_template_string(ADMIN_HTML, **ctx("broadcast"))

@app.route("/admin/logs")
def admin_logs():
    if not session.get("admin"): return redirect("/admin")
    return render_template_string(ADMIN_HTML, **ctx("logs"))

@app.route("/admin/settings")
def admin_settings():
    if not session.get("admin"): return redirect("/admin")
    return render_template_string(ADMIN_HTML, **ctx("settings"))

# ── Start ─────────────────────────────────────────────────────────────────────
def run_bot():
    print("🤖 Bot polling...")
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    print(f"🌐 Server on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
