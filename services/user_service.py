"""User va balans boshqaruv blueprint"""
from flask import Blueprint, render_template, request, session, redirect, url_for, flash, jsonify
from database.db import get_db, r2d, r2l
from services.order_service import place_order, sync_all_active
from auth.auth_middleware import login_required
from services.payment_service import payme_create, usdt_create, usdt_check
from utils.security import gen_key
from config import Config

user_bp = Blueprint("user", __name__)


# ── Current user helper ─────────────────────────────────────────────────────
def current_user():
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()


# ── DASHBOARD ────────────────────────────────────────────────────────────────
@user_bp.route("/dashboard")
@login_required
def dashboard():
    db  = get_db()
    u   = current_user()
    stats = {
        "total_orders": db.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (u["id"],)).fetchone()[0],
        "completed":    db.execute("SELECT COUNT(*) FROM orders WHERE user_id=? AND status='Completed'", (u["id"],)).fetchone()[0],
        "pending":      db.execute("SELECT COUNT(*) FROM orders WHERE user_id=? AND status IN ('Pending','Processing')", (u["id"],)).fetchone()[0],
        "total_spent":  u["total_spent"],
    }
    recent = r2l(db.execute(
        "SELECT o.*, s.name as svc_name FROM orders o "
        "JOIN services s ON o.service_id=s.id "
        "WHERE o.user_id=? ORDER BY o.created_at DESC LIMIT 5",
        (u["id"],)
    ).fetchall())
    return render_template("dashboard.html", user=r2d(u), stats=stats, recent=recent)


# ── YANGI ORDER ──────────────────────────────────────────────────────────────
@user_bp.route("/new-order", methods=["GET", "POST"])
@login_required
def new_order():
    db   = get_db()
    u    = current_user()
    cats = r2l(db.execute("SELECT * FROM categories WHERE is_active=1 ORDER BY sort_order").fetchall())
    svcs = r2l(db.execute(
        "SELECT s.*, c.name as cat_name FROM services s "
        "JOIN categories c ON s.category_id=c.id WHERE s.is_active=1 ORDER BY c.sort_order, s.id"
    ).fetchall())
    if request.method == "POST":
        svc_id = int(request.form.get("service_id", 0))
        link   = request.form.get("link", "").strip()
        qty    = int(request.form.get("quantity", 0))
        result = place_order(svc_id, link, qty)
        if result.get("ok"):
            flash(f"✅ Order #{result['order_id']} yaratildi! Narx: {result['total_price']:,.0f} so'm", "success")
            return redirect(url_for("user.orders"))
        flash(result.get("error", "Xato yuz berdi"), "error")
    return render_template("new_order.html", user=r2d(u), categories=cats, services=svcs)


# ── ORDERLAR ─────────────────────────────────────────────────────────────────
@user_bp.route("/orders")
@login_required
def orders():
    db     = get_db()
    u      = current_user()
    page   = max(1, int(request.args.get("page", 1)))
    status = request.args.get("status", "")
    limit  = 20
    where  = "WHERE o.user_id=?"
    params = [u["id"]]
    if status:
        where += " AND o.status=?"
        params.append(status)
    rows = r2l(db.execute(
        f"SELECT o.*, s.name as svc_name FROM orders o "
        f"JOIN services s ON o.service_id=s.id "
        f"{where} ORDER BY o.created_at DESC LIMIT ? OFFSET ?",
        params + [limit, (page - 1) * limit]
    ).fetchall())
    total = db.execute(f"SELECT COUNT(*) FROM orders o {where}", params).fetchone()[0]
    return render_template("orders.html", user=r2d(u), orders=rows,
                           page=page, total=total, limit=limit, status=status)


# ── BALANS TO'LDIRISH ────────────────────────────────────────────────────────
@user_bp.route("/add-funds", methods=["GET", "POST"])
@login_required
def add_funds():
    db = get_db()
    u  = current_user()

    if request.method == "POST":
        import os, time
        method     = request.form.get("method", "Karta")
        amount_str = request.form.get("amount", "0").replace(",", "").replace(" ", "")
        try:
            amount = int(float(amount_str))
        except:
            flash("Summa noto'g'ri", "error")
            return redirect(url_for("user.add_funds"))

        if amount < Config.MIN_DEPOSIT:
            flash(f"Minimal: {Config.MIN_DEPOSIT:,} so'm", "error")
            return redirect(url_for("user.add_funds"))

        check_file = request.files.get("check_file")
        if not check_file or check_file.filename == "":
            flash("Iltimos, to'lov chekini yuklang", "warning")
            return redirect(url_for("user.add_funds"))

        # Faylni saqlash
        UPLOAD_FOLDER = os.path.join("static", "uploads", "checks")
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        ext      = check_file.filename.rsplit(".", 1)[-1].lower()
        filename = f"check_{u['id']}_{int(time.time())}.{ext}"
        check_file.save(os.path.join(UPLOAD_FOLDER, filename))
        check_url = f"/static/uploads/checks/{filename}"

        # DB ga saqlash
        cur = db.execute(
            "INSERT INTO deposits (user_id, amount, method, status, tx_hash) VALUES (?,?,?,?,?)",
            (u["id"], amount, method, "pending", check_url)
        )
        db.commit()

        flash(f"✅ Chek qabul qilindi! Admin 5-15 daqiqa ichida tasdiqlaydi.", "success")
        return redirect(url_for("user.add_funds"))

    history = r2l(db.execute(
        "SELECT * FROM deposits WHERE user_id=? ORDER BY created_at DESC LIMIT 20",
        (u["id"],)
    ).fetchall())
    return render_template("add_funds.html", user=r2d(u), history=history,
                           card_number="5614 6835 8365 4223",
                           card_owner="Iskandarov Azizbek")

@user_bp.route("/add-funds/usdt/check", methods=["POST"])
@login_required
def usdt_check_view():
    d      = request.get_json() or {}
    dep_id = d.get("deposit_id")
    tx     = d.get("tx_hash", "")
    db     = get_db()
    dep    = db.execute("SELECT * FROM deposits WHERE id=? AND user_id=?",
                        (dep_id, session["user_id"])).fetchone()
    if not dep:
        return jsonify({"ok": False, "message": "Topilmadi"})
    parts   = (dep["external_id"] or "usdt_0").split("_")
    amt_usd = float(parts[1]) if len(parts) > 1 else 0
    r = usdt_check(dep_id, session["user_id"], dep["amount"], amt_usd,
                   Config.USDT_WALLET, dep["created_at"], tx)
    return jsonify(r)





@user_bp.route("/profile/regen-key", methods=["POST"])
@login_required
def regen_key():
    db = get_db()
    db.execute("UPDATE users SET api_key=? WHERE id=?", (gen_key(), session["user_id"]))
    db.commit()
    flash("API key yangilandi!", "success")
    return redirect(url_for("user.api_docs"))


# ── API DOCS ──────────────────────────────────────────────────────────────────
@user_bp.route("/api-docs")
@login_required
def api_docs():
    u = current_user()
    return render_template("api.html", user=r2d(u), site_url=Config.SITE_URL)


# ── ORDER PRICE (AJAX) ────────────────────────────────────────────────────────
@user_bp.route("/api/price")
@login_required
def get_price():
    svc_id = int(request.args.get("service_id", 0))
    qty    = int(request.args.get("quantity", 0))
    db     = get_db()
    # ✅ Narx bazadan olinadi — allaqachon so'mda, 4% ustama bilan
    svc = db.execute(
        "SELECT price_per_1000 FROM services WHERE id=? AND is_active=1", (svc_id,)
    ).fetchone()
    if not svc or qty <= 0:
        return jsonify({"price": 0, "formatted": "0"})
    price = round(svc["price_per_1000"] * qty / 1000, 2)
    return jsonify({"price": price, "formatted": f"{price:,.0f}"})


# ── SYNC ORDER STATUS (AJAX) ──────────────────────────────────────────────────
@user_bp.route("/api/sync-orders", methods=["POST"])
@login_required
def sync_orders():
    sync_all_active()
    return jsonify({"ok": True, "message": "Yangilanmoqda..."})


# ── PROFIL ───────────────────────────────────────────────────────────────────
@user_bp.route("/profile")
@login_required
def profile():
    db  = get_db()
    u   = current_user()
    txs = r2l(db.execute(
        "SELECT * FROM transactions WHERE user_id=? ORDER BY created_at DESC LIMIT 30",
        (u["id"],)
    ).fetchall())
    stats = {
        "total_orders": db.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (u["id"],)).fetchone()[0],
        "completed":    db.execute("SELECT COUNT(*) FROM orders WHERE user_id=? AND status='Completed'", (u["id"],)).fetchone()[0],
        "pending":      db.execute("SELECT COUNT(*) FROM orders WHERE user_id=? AND status IN ('Pending','Processing')", (u["id"],)).fetchone()[0],
        "total_spent":  u["total_spent"],
    }

    return render_template("profile.html", user=r2d(u), transactions=txs, stats=stats)
