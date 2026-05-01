import os, sqlite3
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, jsonify, flash)
from functools import wraps
from config import Config
from utils.logger import log

balance_bp = Blueprint("balance", __name__)

UPLOAD_FOLDER = os.path.join("static", "uploads", "checks")
ALLOWED_EXT   = {"png", "jpg", "jpeg", "webp", "gif"}
CARD_NUMBER   = "5614 6835 8365 4223"
CARD_OWNER    = "Iskandarov Azizbek"
ADMIN_TG      = "https://t.me/yakkavazir"   # adminga xabar yuborish

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── helpers ──────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return f(*a, **kw)
    return wrap

def admin_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if session.get("role") != "admin":
            return jsonify({"ok": False, "message": "Ruxsat yo'q"}), 403
        return f(*a, **kw)
    return wrap

def allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def get_db():
    return sqlite3.connect(Config.DB_PATH, check_same_thread=False)

def notify_admin_tg(deposit_id, username, amount, method, check_url):
    """Telegram botga xabar yuborish (agar BOT_TOKEN va ADMIN_CHAT_ID config da bo'lsa)"""
    token   = getattr(Config, "BOT_TOKEN", None)
    chat_id = getattr(Config, "ADMIN_CHAT_ID", None)
    if not token or not chat_id:
        return
    try:
        import urllib.request, urllib.parse, json as _json
        text = (
            f"💳 <b>Yangi to'lov cheki</b>\n\n"
            f"🆔 Deposit: <code>#{deposit_id}</code>\n"
            f"👤 Foydalanuvchi: <b>{username}</b>\n"
            f"💰 Summa: <b>{amount:,.0f} so'm</b>\n"
            f"🏦 Usul: {method}\n"
            f"🖼 Chek: {check_url}\n\n"
            f"⚠️ Karta egasi: <b>{CARD_OWNER}</b>\n"
            f"Tasdiqlash: /admin/payments"
        )
        data = urllib.parse.urlencode({
            "chat_id":    chat_id,
            "text":       text,
            "parse_mode": "HTML"
        }).encode()
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, timeout=5
        )
    except Exception as e:
        log.error("TG notify xato: %s", e)

# ── FOYDALANUVCHI: To'lov sahifasi ───────────────────────────
@balance_bp.route("/add-funds", methods=["GET", "POST"])
@login_required
def add_funds():
    db      = get_db()
    user_id = session["user_id"]

    # To'lov tarixi
    history = db.execute(
        "SELECT * FROM deposits WHERE user_id=? ORDER BY created_at DESC LIMIT 20",
        (user_id,)
    ).fetchall()
    history = [dict(zip([c[0] for c in db.execute("SELECT * FROM deposits LIMIT 0").description
                         ], [])) or dict(h) for h in history]
    # sqlite3.Row ni dict ga aylantiramiz
    history_list = []
    for row in db.execute(
        "SELECT * FROM deposits WHERE user_id=? ORDER BY created_at DESC LIMIT 20",
        (user_id,)
    ).fetchall():
        history_list.append({
            "id":         row[0],
            "user_id":    row[1],
            "amount":     row[2],
            "method":     row[3],
            "status":     row[4],
            "created_at": row[8] or "",
        })

    user_row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    user     = {"balance": user_row[4] if user_row else 0,
                "username": session.get("username", "")}

    if request.method == "POST":
        amount_str = request.form.get("amount", "0").replace(",", "").replace(" ", "")
        method     = request.form.get("method", "Karta")
        check_file = request.files.get("check_file")

        # Validatsiya
        try:
            amount = float(amount_str)
        except ValueError:
            flash("Summa noto'g'ri kiritildi", "error")
            return redirect(url_for("balance.add_funds"))

        if amount < 5000:
            flash("Minimal to'lov miqdori 5,000 so'm", "warning")
            return redirect(url_for("balance.add_funds"))

        if not check_file or check_file.filename == "":
            flash("Iltimos, to'lov chekini yuklang", "warning")
            return redirect(url_for("balance.add_funds"))

        if not allowed(check_file.filename):
            flash("Faqat rasm fayllari qabul qilinadi (PNG, JPG, WEBP)", "error")
            return redirect(url_for("balance.add_funds"))

        # Faylni saqlash
        import time
        ext      = check_file.filename.rsplit(".", 1)[1].lower()
        filename = f"check_{user_id}_{int(time.time())}.{ext}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        check_file.save(filepath)
        check_url = f"/static/uploads/checks/{filename}"

        # DB ga yozish
        cur = db.execute(
            "INSERT INTO deposits (user_id, amount, method, status, tx_hash) VALUES (?,?,?,?,?)",
            (user_id, amount, method, "pending", check_url)
        )
        deposit_id = cur.lastrowid
        db.execute(
            "INSERT INTO transactions (user_id,type,amount,description,status) VALUES (?,?,?,?,?)",
            (user_id, "credit", amount, f"Chek yuborildi — {method}", "pending")
        )
        db.commit()

        # Adminga Telegram xabar
        notify_admin_tg(deposit_id, session.get("username",""), amount, method,
                        request.host_url.rstrip("/") + check_url)

        flash(f"✅ Chek qabul qilindi! #{deposit_id} — Admin 5-15 daqiqa ichida tasdiqlaydi.", "success")
        return redirect(url_for("balance.add_funds"))

    return render_template("add_funds.html",
                           user=user,
                           history=history_list,
                           card_number=CARD_NUMBER,
                           card_owner=CARD_OWNER)


# ── ADMIN: Chekni ko'rish va tasdiqlash ──────────────────────
@balance_bp.route("/admin/payments/<int:dep_id>/confirm", methods=["POST"])
@login_required
@admin_required
def admin_confirm(dep_id):
    db  = get_db()
    dep = db.execute("SELECT * FROM deposits WHERE id=?", (dep_id,)).fetchone()
    if not dep:
        return jsonify({"ok": False, "message": "Topilmadi"})
    if dep[4] == "completed":
        return jsonify({"ok": False, "message": "Allaqachon tasdiqlangan"})

    amount  = dep[2]
    user_id = dep[1]

    db.execute("UPDATE deposits SET status='completed', confirmed_at=datetime('now') WHERE id=?", (dep_id,))
    db.execute("UPDATE users SET balance=balance+? WHERE id=?", (amount, user_id))
    db.execute(
        "UPDATE transactions SET status='completed' WHERE user_id=? AND description LIKE ? AND status='pending'",
        (user_id, f"%#{dep_id}%")
    )
    db.execute(
        "INSERT INTO transactions (user_id,type,amount,description,ref_id,status) VALUES (?,?,?,?,?,?)",
        (user_id, "credit", amount, f"Balans to'ldirildi — chek #{dep_id}", str(dep_id), "completed")
    )
    db.commit()
    log.info("Admin confirmed deposit #%s user=%s amount=%s", dep_id, user_id, amount)
    return jsonify({"ok": True})


@balance_bp.route("/admin/payments/<int:dep_id>/reject", methods=["POST"])
@login_required
@admin_required
def admin_reject(dep_id):
    db = get_db()
    db.execute("UPDATE deposits SET status='rejected' WHERE id=? AND status='pending'", (dep_id,))
    db.commit()
    return jsonify({"ok": True})


@balance_bp.route("/admin/payments")
@login_required
@admin_required
def admin_payments():
    db = get_db()
    rows = db.execute("""
        SELECT d.id, d.user_id, u.username, d.amount, d.method,
               d.status, d.tx_hash, d.created_at
        FROM deposits d
        JOIN users u ON u.id = d.user_id
        ORDER BY d.created_at DESC
        LIMIT 200
    """).fetchall()
    payments = [{"id": r[0], "user_id": r[1], "username": r[2],
                 "amount": r[3], "method": r[4], "status": r[5],
                 "check_url": r[6], "created_at": r[7] or ""} for r in rows]
    pending_count = sum(1 for p in payments if p["status"] == "pending")
    return render_template("admin/payments.html",
                           payments=payments,
                           pending_count=pending_count)
