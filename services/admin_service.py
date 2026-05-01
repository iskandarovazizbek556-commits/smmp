from flask import Blueprint, render_template, request, session, redirect, url_for, flash, jsonify
from database.db import get_db, r2d, r2l
from auth.auth_middleware import admin_required
from providers.smm_api1 import get_balance as provider_balance
from services.order_service import sync_all_active
from config import Config
import time

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

CURRENCY_RATE = 12500
MARKUP        = 1.04

# ── Cache ─────────────────────────────────────────────────────────────────────
_cache = {}
def cache_get(key):
    item = _cache.get(key)
    if item and time.time() - item["ts"] < 300:
        return item["val"]
    return None

def cache_set(key, val):
    _cache[key] = {"val": val, "ts": time.time()}

def cache_clear():
    _cache.clear()


# ── DASHBOARD ─────────────────────────────────────────────────────────────────
@admin_bp.route("/")
@admin_required
def dashboard():
    db    = get_db()
    today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
    stats = {
        "total_users":    db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "total_orders":   db.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        "today_orders":   db.execute("SELECT COUNT(*) FROM orders WHERE date(created_at)=?", (today,)).fetchone()[0],
        "today_revenue":  db.execute("SELECT COALESCE(SUM(amount),0) FROM deposits WHERE date(created_at)=? AND status='completed'", (today,)).fetchone()[0],
        "total_revenue":  db.execute("SELECT COALESCE(SUM(amount),0) FROM deposits WHERE status='completed'").fetchone()[0],
        "pending_orders": db.execute("SELECT COUNT(*) FROM orders WHERE status IN ('Pending','Processing')").fetchone()[0],
        "pending_deps":   db.execute("SELECT COUNT(*) FROM deposits WHERE status='pending'").fetchone()[0],
    }
    recent_orders = r2l(db.execute(
        "SELECT o.id, o.status, o.price, o.quantity, o.created_at, "
        "u.username, s.name as svc_name "
        "FROM orders o "
        "JOIN users u ON o.user_id=u.id "
        "JOIN services s ON o.service_id=s.id "
        "ORDER BY o.created_at DESC LIMIT 10"
    ).fetchall())
    return render_template("admin/admin_dashboard.html", stats=stats, recent=recent_orders)


# ── XIZMATLAR ─────────────────────────────────────────────────────────────────
@admin_bp.route("/services")
@admin_required
def services():
    db   = get_db()
    svcs = r2l(db.execute(
        "SELECT s.id, s.name, s.name_uz, s.description_uz, s.type, s.price_per_1000, "
        "s.min_order, s.max_order, s.is_active, s.is_recommended, s.provider_id, c.name as cat_name "
        "FROM services s "
        "JOIN categories c ON s.category_id=c.id "
        "ORDER BY c.sort_order, s.id"
    ).fetchall())
    cats = r2l(db.execute("SELECT * FROM categories ORDER BY sort_order").fetchall())
    return render_template("admin/services.html", services=svcs, categories=cats)


# ── ID BO'YICHA QIDIRISH (AJAX) ───────────────────────────────────────────────
@admin_bp.route("/services/search-by-id", methods=["GET"])
@admin_required
def search_service_by_id():
    """Provider ID bo'yicha xizmat ma'lumotlarini provayderdan olish"""
    provider_id = request.args.get("provider_id", "").strip()
    if not provider_id:
        return jsonify({"ok": False, "message": "ID kiriting"})

    import requests as _req
    try:
        url  = f"{Config.PROVIDER_URL}?action=services&key={Config.PROVIDER_KEY}"
        cached = cache_get("all_services")
        if cached:
            all_svcs = cached
        else:
            resp = _req.get(url, timeout=15)
            all_svcs = resp.json()
            cache_set("all_services", all_svcs)

        if not isinstance(all_svcs, list):
            return jsonify({"ok": False, "message": "Provider xatosi"})

        # ID bo'yicha qidirish
        found = None
        for s in all_svcs:
            if str(s.get("service", "")) == str(provider_id):
                found = s
                break

        if not found:
            return jsonify({"ok": False, "message": f"ID {provider_id} topilmadi"})

        raw_rate       = float(found.get("rate", 0))
        price_per_1000 = round(raw_rate * CURRENCY_RATE * MARKUP, 2)

        return jsonify({
            "ok": True,
            "data": {
                "provider_id":   found["service"],
                "name":          found["name"],
                "category":      found.get("category", ""),
                "type":          found.get("type", "Default"),
                "price_per_1000": price_per_1000,
                "min_order":     int(found.get("min", 10)),
                "max_order":     int(found.get("max", 100000)),
                "rate_usd":      raw_rate,
            }
        })
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)})


@admin_bp.route("/services/add", methods=["POST"])
@admin_required
def add_service():
    d  = request.form
    db = get_db()
    db.execute(
        "INSERT INTO services (category_id, provider_id, name, name_uz, description, description_uz, "
        "type, price_per_1000, min_order, max_order, is_recommended) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (d["category_id"], d.get("provider_id") or None, d["name"],
         d.get("name_uz", ""), d.get("description", ""), d.get("description_uz", ""),
         d.get("type", "Default"), float(d["price_per_1000"]),
         int(d["min_order"]), int(d["max_order"]),
         int(d.get("is_recommended", 0)))
    )
    db.commit()
    cache_clear()
    flash("Xizmat qo'shildi!", "success")
    return redirect(url_for("admin.services"))


@admin_bp.route("/services/<int:sid>", methods=["POST"])
@admin_required
def update_service(sid):
    d  = request.form
    db = get_db()
    db.execute(
        "UPDATE services SET name=?, name_uz=?, price_per_1000=?, min_order=?, max_order=?, "
        "is_active=?, description=?, description_uz=?, type=?, is_recommended=? WHERE id=?",
        (d["name"], d.get("name_uz", ""), float(d["price_per_1000"]),
         int(d["min_order"]), int(d["max_order"]),
         int(d.get("is_active", 1)), d.get("description", ""),
         d.get("description_uz", ""), d.get("type", "Default"),
         int(d.get("is_recommended", 0)), sid)
    )
    db.commit()
    cache_clear()
    return jsonify({"ok": True})


# ── TAVSIYA ETILGAN XIZMATNI BELGILASH ───────────────────────────────────────
@admin_bp.route("/services/<int:sid>/recommend", methods=["POST"])
@admin_required
def toggle_recommend(sid):
    db  = get_db()
    svc = db.execute("SELECT is_recommended FROM services WHERE id=?", (sid,)).fetchone()
    if not svc:
        return jsonify({"ok": False})
    new_val = 0 if svc["is_recommended"] else 1
    db.execute("UPDATE services SET is_recommended=? WHERE id=?", (new_val, sid))
    db.commit()
    cache_clear()
    return jsonify({"ok": True, "is_recommended": new_val})


@admin_bp.route("/services/import", methods=["POST"])
@admin_required
def import_services():
    """Provider dan xizmatlarni import qilish — avto ID, narx so'mda, 4% ustama"""
    import requests as _req
    try:
        url  = f"{Config.PROVIDER_URL}?action=services&key={Config.PROVIDER_KEY}"
        resp = _req.get(url, timeout=15)
        svcs = resp.json()
    except Exception as e:
        flash(f"API xatosi: {e}", "error")
        return redirect(url_for("admin.services"))

    if not isinstance(svcs, list):
        flash("API noto'g'ri format qaytardi", "error")
        return redirect(url_for("admin.services"))

    db    = get_db()
    count = 0
    updated = 0

    for s in svcs:
        raw_rate       = float(s.get("rate", 0))
        price_per_1000 = round(raw_rate * CURRENCY_RATE * MARKUP, 2)

        cat_name = s.get("category", "Boshqa")
        cat = db.execute("SELECT id FROM categories WHERE name=?", (cat_name,)).fetchone()
        if not cat:
            cur    = db.execute("INSERT INTO categories (name) VALUES (?)", (cat_name,))
            cat_id = cur.lastrowid
        else:
            cat_id = cat["id"]

        # provider_id = provayderning o'z ID si (avto saqlanadi)
        existing = db.execute("SELECT id FROM services WHERE provider_id=?", (str(s["service"]),)).fetchone()
        if existing:
            db.execute(
                "UPDATE services SET name=?, type=?, price_per_1000=?, "
                "min_order=?, max_order=?, category_id=? WHERE provider_id=?",
                (s["name"], s.get("type", "Default"), price_per_1000,
                 int(s.get("min", 10)), int(s.get("max", 100000)), cat_id, str(s["service"]))
            )
            updated += 1
        else:
            db.execute(
                "INSERT INTO services (category_id, provider_id, name, type, price_per_1000, min_order, max_order) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (cat_id, str(s["service"]), s["name"], s.get("type", "Default"),
                 price_per_1000, int(s.get("min", 10)), int(s.get("max", 100000)))
            )
            count += 1

    db.commit()
    cache_clear()
    flash(f"✅ {count} yangi + {updated} yangilandi. Narxlar so'mda (4% ustama)", "success")
    return redirect(url_for("admin.services"))


# ── FOYDALANUVCHILAR ──────────────────────────────────────────────────────────
@admin_bp.route("/users")
@admin_required
def users():
    db = get_db()
    q  = request.args.get("q", "")
    page  = max(1, int(request.args.get("page", 1)))
    limit = 50
    if q:
        rows = r2l(db.execute(
            "SELECT u.*, (SELECT COUNT(*) FROM orders WHERE user_id=u.id) as order_count "
            "FROM users u WHERE username LIKE ? OR email LIKE ? "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (f"%{q}%", f"%{q}%", limit, (page-1)*limit)
        ).fetchall())
        total = db.execute("SELECT COUNT(*) FROM users WHERE username LIKE ? OR email LIKE ?",
                           (f"%{q}%", f"%{q}%")).fetchone()[0]
    else:
        rows = r2l(db.execute(
            "SELECT u.*, (SELECT COUNT(*) FROM orders WHERE user_id=u.id) as order_count "
            "FROM users u ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, (page-1)*limit)
        ).fetchall())
        total = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    return render_template("admin/users.html", users=rows, q=q, page=page, total=total, limit=limit)


@admin_bp.route("/users/<int:uid>/balance", methods=["POST"])
@admin_required
def user_balance(uid):
    amt = float(request.form.get("amount", 0))
    db  = get_db()
    db.execute("UPDATE users SET balance=balance+? WHERE id=?", (amt, uid))
    db.execute(
        "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
        (uid, "credit" if amt > 0 else "debit", abs(amt), "Admin tomonidan")
    )
    db.commit()
    return jsonify({"ok": True})


@admin_bp.route("/users/<int:uid>/toggle", methods=["POST"])
@admin_required
def user_toggle(uid):
    db = get_db()
    u  = db.execute("SELECT is_active FROM users WHERE id=?", (uid,)).fetchone()
    db.execute("UPDATE users SET is_active=? WHERE id=?", (0 if u["is_active"] else 1, uid))
    db.commit()
    return jsonify({"ok": True})


# ── ORDERLAR ──────────────────────────────────────────────────────────────────
@admin_bp.route("/orders")
@admin_required
def orders():
    db     = get_db()
    status = request.args.get("status", "")
    q      = request.args.get("q", "")
    page   = max(1, int(request.args.get("page", 1)))
    limit  = 50
    where, params = [], []
    if status:
        where.append("o.status=?")
        params.append(status)
    if q:
        where.append("(u.username LIKE ? OR o.link LIKE ? OR CAST(o.id AS TEXT)=?)")
        params += [f"%{q}%", f"%{q}%", q]
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    sql = (
        "SELECT o.id, o.status, o.price, o.quantity, o.link, o.created_at, "
        "u.username, s.name as svc_name "
        "FROM orders o "
        "JOIN users u ON o.user_id=u.id "
        "JOIN services s ON o.service_id=s.id"
        + where_sql
        + " ORDER BY o.created_at DESC LIMIT ? OFFSET ?"
    )
    rows  = r2l(db.execute(sql, params + [limit, (page-1)*limit]).fetchall())
    total = db.execute(
        "SELECT COUNT(*) FROM orders o JOIN users u ON o.user_id=u.id" + where_sql, params
    ).fetchone()[0]
    return render_template("admin/orders.html", orders=rows, page=page,
                           total=total, limit=limit, status=status, q=q)


@admin_bp.route("/orders/<int:oid>/status", methods=["POST"])
@admin_required
def order_status(oid):
    st = request.form.get("status")
    db = get_db()
    db.execute("UPDATE orders SET status=?, updated_at=datetime('now') WHERE id=?", (st, oid))
    db.commit()
    return jsonify({"ok": True})


@admin_bp.route("/orders/sync", methods=["POST"])
@admin_required
def sync_orders():
    sync_all_active()
    flash("Orderlar yangilanmoqda...", "success")
    return redirect(url_for("admin.orders"))


@admin_bp.route("/payments")
@admin_required
def payments():
    db    = get_db()
    page  = max(1, int(request.args.get("page", 1)))
    limit = 50
    rows = r2l(db.execute(
        "SELECT d.id, d.amount, d.method, d.status, d.tx_hash as check_url, "
        "d.created_at, d.confirmed_at, u.username "
        "FROM deposits d "
        "JOIN users u ON d.user_id=u.id "
        "ORDER BY d.created_at DESC LIMIT ? OFFSET ?",
        (limit, (page-1)*limit)
    ).fetchall())
    total         = db.execute("SELECT COUNT(*) FROM deposits").fetchone()[0]
    pending_count = db.execute("SELECT COUNT(*) FROM deposits WHERE status='pending'").fetchone()[0]
    return render_template("admin/payments.html",
                           payments=rows,
                           page=page,
                           total=total,
                           limit=limit,
                           pending_count=pending_count)

@admin_bp.route("/payments/<int:did>/confirm", methods=["POST"])
@admin_required
def confirm_payment(did):
    db  = get_db()
    dep = db.execute("SELECT * FROM deposits WHERE id=?", (did,)).fetchone()
    if dep and dep["status"] == "pending":
        db.execute(
            "UPDATE deposits SET status='completed', confirmed_at=datetime('now') WHERE id=?", (did,)
        )
        db.execute("UPDATE users SET balance=balance+? WHERE id=?", (dep["amount"], dep["user_id"]))
        db.execute(
            "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
            (dep["user_id"], "credit", dep["amount"], f"Admin tasdiqladi #{did}")
        )
        db.commit()
        return jsonify({"ok": True})
    return jsonify({"ok": False, "message": "Topilmadi yoki allaqachon tasdiqlangan"})


# ── SOZLAMALAR ────────────────────────────────────────────────────────────────
@admin_bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    db = get_db()
    if request.method == "POST":
        for key, val in request.form.items():
            db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val))
        db.commit()
        flash("Saqlandi!", "success")
    cfg      = {r["key"]: r["value"] for r in db.execute("SELECT * FROM settings").fetchall()}
    prov_bal = provider_balance()
    return render_template("admin/settings.html", cfg=cfg, provider_balance=prov_bal)