import os
import threading
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, session, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

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

db = {
    "users": {},
    "blocked": set(),
    "broadcast_log": [],
    "stats": {
        "total_starts": 0,
        "total_verifications": 0,
        "total_denied": 0,
        "total_verify_calls": 0,
        "total_resets": 0,
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
            "key_version": 1,   # <-- session version tracking
            "reset_count": 0,
        }
    if verified:
        db["users"][uid]["verified"] = True
        db["users"][uid]["api_calls"] += 1
        db["users"][uid]["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M")

# ── /verify/<uid> ── returns allowed + key_version so extension can detect resets
@app.route("/verify/<uid>")
def verify_user(uid):
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
    try:
        save_user(m.user, verified=True)
        db["stats"]["total_verifications"] += 1
        username = "@" + m.user.username if m.user.username else m.user.first_name
        kv = db["users"][uid].get("key_version", 1)
        return jsonify({"allowed": True, "username": username, "key_version": kv})
    except:
        return jsonify({"allowed": True, "username": "User", "key_version": 1})

# ── /reset/<uid> ── called by bot button; bumps key_version → invalidates all old extension sessions
@app.route("/reset/<uid>", methods=["POST"])
def reset_key(uid):
    if uid not in db["users"]:
        return jsonify({"success": False, "reason": "unknown_user"})
    if uid in db["blocked"]:
        return jsonify({"success": False, "reason": "blocked"})
    db["users"][uid]["key_version"] = db["users"][uid].get("key_version", 1) + 1
    db["users"][uid]["reset_count"] = db["users"][uid].get("reset_count", 0) + 1
    db["stats"]["total_resets"] += 1
    return jsonify({"success": True, "new_version": db["users"][uid]["key_version"]})

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
        bot.send_message(m.chat.id, "🚫 You have been blocked.")
        return
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK))
    kb.add(InlineKeyboardButton("🔑 Get My API Key", callback_data="get_api"))
    kb.add(InlineKeyboardButton("🔄 Reset My Key", callback_data="reset_key"))
    bot.send_message(m.chat.id,
        f"👋 Welcome *{m.from_user.first_name}*!\n\n1️⃣ Join channel\n2️⃣ Click Get API Key\n3️⃣ Paste in extension\n\n⚠️ Key stops if you leave!\n\n🔄 Use *Reset My Key* if your extension says it's locked in another browser.",
        parse_mode="Markdown", reply_markup=kb)

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
        kb.add(InlineKeyboardButton("🔄 Reset My Key", callback_data="reset_key"))
        bot.edit_message_text(
            f"✅ *Verified!*\n\n🔑 *Your API Key:*\n`{uid}`\n\nPaste in extension!\n\n_Use Reset My Key if locked in another browser._",
            c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=kb)
    else:
        db["stats"]["total_denied"] += 1
        kb.add(InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK))
        kb.add(InlineKeyboardButton("🔄 Try Again", callback_data="get_api"))
        bot.edit_message_text("❌ *Access Denied!*\n\nJoin our channel first!",
            c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=kb)

# ── Reset Key button handler ──
@bot.callback_query_handler(func=lambda c: c.data == "reset_key")
def handle_reset_key(c):
    uid = str(c.from_user.id)
    bot.answer_callback_query(c.id)
    if uid in db["blocked"]:
        bot.answer_callback_query(c.id, "🚫 You are blocked.", show_alert=True)
        return
    if not is_member(int(uid)):
        bot.answer_callback_query(c.id, "❌ Join the channel first!", show_alert=True)
        return
    if uid not in db["users"]:
        save_user(c.from_user)
    db["users"][uid]["key_version"] = db["users"][uid].get("key_version", 1) + 1
    db["users"][uid]["reset_count"] = db["users"][uid].get("reset_count", 0) + 1
    db["stats"]["total_resets"] += 1
    new_v = db["users"][uid]["key_version"]
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📢 Channel", url=CHANNEL_LINK))
    kb.add(InlineKeyboardButton("🔄 Reset Again", callback_data="reset_key"))
    bot.edit_message_text(
        f"🔄 *Key Reset Done!*\n\n✅ All other browsers have been locked out.\n\n🔑 Your API Key is still:\n`{uid}`\n\nNow re-enter it in your extension to unlock.",
        c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=kb)

@bot.message_handler(commands=["reset"])
def tg_reset(m):
    uid = str(m.from_user.id)
    if uid in db["blocked"]:
        bot.send_message(m.chat.id, "🚫 You are blocked.")
        return
    if not is_member(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Join the channel first!")
        return
    if uid not in db["users"]:
        save_user(m.from_user)
    db["users"][uid]["key_version"] = db["users"][uid].get("key_version", 1) + 1
    db["users"][uid]["reset_count"] = db["users"][uid].get("reset_count", 0) + 1
    db["stats"]["total_resets"] += 1
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔄 Reset Again", callback_data="reset_key"))
    bot.send_message(m.chat.id,
        f"🔄 *Key Reset Done!*\n\n✅ All other extensions locked out.\n\n🔑 Your key: `{uid}`\n\nRe-enter it in the extension.",
        parse_mode="Markdown", reply_markup=kb)

@bot.message_handler(commands=["stats"])
def tg_stats(m):
    if m.from_user.id != ADMIN_ID: return
    s = db["stats"]
    bot.send_message(m.chat.id,
        f"📊 *Stats*\n\n👥 Users: `{len(db['users'])}`\n✅ Verified: `{s['total_verifications']}`\n"
        f"🔍 API Calls: `{s['total_verify_calls']}`\n❌ Denied: `{s['total_denied']}`\n"
        f"🔄 Resets: `{s['total_resets']}`\n🚫 Blocked: `{len(db['blocked'])}`",
        parse_mode="Markdown")

@bot.message_handler(commands=["broadcast"])
def tg_broadcast(m):
    if m.from_user.id != ADMIN_ID: return
    text = m.text.replace("/broadcast", "").strip()
    if not text:
        bot.send_message(m.chat.id, "Usage: /broadcast <message>"); return
    sent = 0
    for uid in db["users"]:
        try:
            bot.send_message(int(uid), f"📢 *Announcement*\n\n{text}", parse_mode="Markdown"); sent += 1
        except: pass
    db["broadcast_log"].append({"text": text, "sent_to": sent, "time": datetime.now().strftime("%Y-%m-%d %H:%M")})
    bot.send_message(m.chat.id, f"✅ Sent to {sent} users.")

ADMIN_HTML = """
<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>JV-60FPS Admin</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0}
.sidebar{width:220px;background:#1e293b;height:100vh;position:fixed;padding:24px 0}
.sidebar h2{color:#00e5ff;padding:0 20px 20px;font-size:1rem;border-bottom:1px solid #334155}
.sidebar a{display:block;padding:12px 20px;color:#94a3b8;text-decoration:none;font-size:.88rem}
.sidebar a:hover,.sidebar a.active{background:#334155;color:#00e5ff}
.main{margin-left:220px;padding:30px}
.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:28px}
.topbar h1{font-size:1.3rem}
.logout{background:#ef4444;color:#fff;border:none;padding:8px 16px;border-radius:6px;cursor:pointer;text-decoration:none;font-size:.82rem}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin-bottom:32px}
.card{background:#1e293b;border-radius:12px;padding:20px;border:1px solid #334155}
.card .label{font-size:.75rem;color:#64748b;text-transform:uppercase;letter-spacing:.05em}
.card .value{font-size:2rem;font-weight:700;color:#00e5ff;margin-top:6px}
table{width:100%;border-collapse:collapse;background:#1e293b;border-radius:12px;overflow:hidden}
th{background:#334155;padding:12px 16px;text-align:left;font-size:.75rem;text-transform:uppercase;color:#94a3b8}
td{padding:10px 16px;border-top:1px solid #334155;font-size:.84rem}
tr:hover td{background:#243347}
.badge{display:inline-block;padding:3px 10px;border-radius:999px;font-size:.72rem;font-weight:700}
.badge.active{background:#166534;color:#86efac}
.badge.blocked{background:#7c2d12;color:#fdba74}
.badge.unverified{background:#1e3a5f;color:#93c5fd}
.action-btn{border:none;padding:5px 10px;border-radius:6px;cursor:pointer;font-size:.76rem;font-weight:700;margin:2px}
.btn-red{background:#ef4444;color:#fff}
.btn-green{background:#22c55e;color:#fff}
.btn-orange{background:#f97316;color:#fff}
textarea,input[type=text],input[type=password]{background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:8px;padding:10px 14px;font-size:.88rem;width:100%}
.section-box{background:#1e293b;border-radius:12px;padding:20px;border:1px solid #334155;margin-bottom:20px}
.section-box textarea{height:80px;resize:vertical;margin:10px 0}
.submit-btn{background:#2563eb;color:#fff;border:none;padding:10px 22px;border-radius:8px;cursor:pointer;font-weight:700}
.login-box{max-width:340px;margin:100px auto;background:#1e293b;border-radius:16px;padding:36px;border:1px solid #334155}
.login-box h2{margin-bottom:24px;color:#00e5ff}
.login-box input{margin-bottom:14px}
.alert{background:#7f1d1d;color:#fca5a5;padding:10px 14px;border-radius:8px;margin-bottom:14px;font-size:.85rem}
.flash{background:#14532d;color:#86efac;padding:10px 14px;border-radius:8px;margin-bottom:16px;font-size:.85rem}
.log-item{background:#1e293b;border:1px solid #334155;border-radius:8px;padding:12px 16px;margin-bottom:10px;font-size:.85rem}
.log-time{color:#64748b;font-size:.75rem}
.section-title{font-size:.9rem;font-weight:700;margin-bottom:12px;color:#cbd5e1}
</style></head><body>
{% if not session.get('admin') %}
<div class="login-box">
  <h2>🎮 JV-60FPS Admin</h2>
  {% if error %}<div class="alert">{{ error }}</div>{% endif %}
  <form method="POST" action="/admin/login">
    <input type="password" name="password" placeholder="Admin Password" required><br>
    <button class="submit-btn" style="width:100%;margin-top:4px">Login</button>
  </form>
</div>
{% else %}
<div class="sidebar">
  <h2>🎮 JV-60FPS Admin</h2>
  <a href="/admin"           class="{{ 'active' if page=='dashboard' }}">📊 Dashboard</a>
  <a href="/admin/users"     class="{{ 'active' if page=='users' }}">👥 Users</a>
  <a href="/admin/broadcast" class="{{ 'active' if page=='broadcast' }}">📢 Broadcast</a>
  <a href="/admin/logs"      class="{{ 'active' if page=='logs' }}">📋 Logs</a>
</div>
<div class="main">
  <div class="topbar">
    <h1>
      {% if page=='dashboard' %}📊 Dashboard
      {% elif page=='users' %}👥 Users
      {% elif page=='broadcast' %}📢 Broadcast
      {% elif page=='logs' %}📋 Broadcast Logs
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
      <div class="card"><div class="label">Verify Calls</div><div class="value">{{ stats.verify_calls }}</div></div>
      <div class="card"><div class="label">Key Resets</div><div class="value">{{ stats.resets }}</div></div>
      <div class="card"><div class="label">Denied</div><div class="value">{{ stats.denied }}</div></div>
    </div>

  {% elif page == 'users' %}
    <table>
      <thead><tr><th>ID</th><th>Name</th><th>Username</th><th>Joined</th><th>Last Seen</th><th>Resets</th><th>Status</th><th>Action</th></tr></thead>
      <tbody>
        {% for uid, u in users.items() %}
        <tr>
          <td>{{ uid }}</td><td>{{ u.name }}</td><td>@{{ u.username }}</td>
          <td>{{ u.joined_at }}</td><td>{{ u.last_seen }}</td>
          <td>{{ u.get('reset_count', 0) }}</td>
          <td>
            {% if uid in blocked %}<span class="badge blocked">🚫 Blocked</span>
            {% elif u.verified %}<span class="badge active">✔ Active</span>
            {% else %}<span class="badge unverified">✘ Unverified</span>{% endif %}
          </td>
          <td>
            {% if uid in blocked %}
              <form method="POST" action="/admin/unblock/{{ uid }}" style="display:inline">
                <button class="action-btn btn-green">✅ Unblock</button></form>
            {% else %}
              <form method="POST" action="/admin/block/{{ uid }}" style="display:inline">
                <button class="action-btn btn-red">🚫 Block</button></form>
            {% endif %}
            <form method="POST" action="/admin/reset/{{ uid }}" style="display:inline">
              <button class="action-btn btn-orange">🔄 Reset Key</button></form>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>

  {% elif page == 'broadcast' %}
    <div class="section-box">
      <div class="section-title">Send to all users</div>
      <form method="POST" action="/admin/broadcast">
        <textarea name="message" placeholder="Message..."></textarea>
        <button class="submit-btn">📢 Send</button>
      </form>
    </div>

  {% elif page == 'logs' %}
    {% if not logs %}<p style="color:#64748b">No broadcasts yet.</p>{% endif %}
    {% for log in logs|reverse %}
      <div class="log-item">
        <div class="log-time">{{ log.time }} — {{ log.sent_to }} users</div>
        <div style="margin-top:6px">{{ log.text }}</div>
      </div>
    {% endfor %}
  {% endif %}
</div>
{% endif %}
</body></html>
"""

def ctx(page, flash="", error=""):
    s = db["stats"]
    return {
        "page": page, "flash": flash, "error": error,
        "stats": {
            "users": len(db["users"]),
            "verified": sum(1 for u in db["users"].values() if u["verified"]),
            "blocked": len(db["blocked"]),
            "starts": s["total_starts"],
            "verifications": s["total_verifications"],
            "denied": s["total_denied"],
            "verify_calls": s["total_verify_calls"],
            "resets": s["total_resets"],
        },
        "users": db["users"],
        "blocked": db["blocked"],
        "logs": db["broadcast_log"],
    }

@app.route("/")
def index():
    return '🤖 JV-60FPS Bot running! <a href="/admin">Admin Panel</a>'

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
    return render_template_string(ADMIN_HTML, **ctx("users", flash=f"🚫 User {uid} blocked."))

@app.route("/admin/unblock/<uid>", methods=["POST"])
def admin_unblock(uid):
    if not session.get("admin"): return redirect("/admin")
    db["blocked"].discard(uid)
    return render_template_string(ADMIN_HTML, **ctx("users", flash=f"✅ User {uid} unblocked."))

@app.route("/admin/reset/<uid>", methods=["POST"])
def admin_reset_key(uid):
    if not session.get("admin"): return redirect("/admin")
    if uid in db["users"]:
        db["users"][uid]["key_version"] = db["users"][uid].get("key_version", 1) + 1
        db["users"][uid]["reset_count"] = db["users"][uid].get("reset_count", 0) + 1
        db["stats"]["total_resets"] += 1
    return render_template_string(ADMIN_HTML, **ctx("users", flash=f"🔄 Key reset for user {uid}."))

@app.route("/admin/broadcast", methods=["GET","POST"])
def admin_broadcast():
    if not session.get("admin"): return redirect("/admin")
    if request.method == "POST":
        text = request.form.get("message","").strip()
        if text:
            sent = 0
            for uid in db["users"]:
                try:
                    bot.send_message(int(uid), f"📢 *Announcement*\n\n{text}", parse_mode="Markdown"); sent += 1
                except: pass
            db["broadcast_log"].append({"text": text, "sent_to": sent, "time": datetime.now().strftime("%Y-%m-%d %H:%M")})
            return render_template_string(ADMIN_HTML, **ctx("broadcast", flash=f"✅ Sent to {sent} users!"))
    return render_template_string(ADMIN_HTML, **ctx("broadcast"))

@app.route("/admin/logs")
def admin_logs():
    if not session.get("admin"): return redirect("/admin")
    return render_template_string(ADMIN_HTML, **ctx("logs"))

def run_bot():
    print("🤖 Bot polling...")
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    print(f"🌐 Server on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
