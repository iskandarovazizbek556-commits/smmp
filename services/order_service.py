# services/order_service.py

import json, urllib.request, urllib.parse
from config import Config
from utils.logger import log
from database.db import get_db

API_URL       = Config.PROVIDER_URL
API_KEY       = Config.PROVIDER_KEY
CURRENCY_RATE = 12500   # 1 USD = 12500 so'm
MARKUP        = 1.04    # 4% ustama


# ─── Ichki API so'rov ─────────────────────────────────────────────────────────
def _call(action, extra=None):
    params = {"key": API_KEY, "action": action}
    if extra:
        params.update(extra)
    try:
        data = urllib.parse.urlencode(params).encode()
        req  = urllib.request.Request(
            API_URL, data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
        return resp
    except Exception as e:
        log.error("1xPanel API xato [%s]: %s", action, e)
        return {"error": str(e)}


# ─── Xizmatlarni olish ───────────────────────────────────────────────────────
def get_services():
    """Barcha xizmatlar, narx: so'mda, 4% ustama bilan"""
    services = _call("services")
    if not isinstance(services, list):
        return []
    updated = []
    for s in services:
        try:
            provider_rate = float(s.get("rate", 0))   # ✅ "rate" - to'g'ri field
            # 1000 ta uchun USD narx -> 1 ta uchun so'm + 4%
            price_per_unit = (provider_rate / 1000) * CURRENCY_RATE * MARKUP
            s["price"]   = round(price_per_unit, 2)   # 1 ta uchun narx
            s["service"] = int(s.get("service", 0))   # ✅ "service" - to'g'ri field
            updated.append(s)
        except Exception as e:
            log.error("Narx hisoblash xato: %s", e)
    return updated


# ─── Buyurtma yaratish ───────────────────────────────────────────────────────
def create_order(service_id, link, quantity):
    db = get_db()
    user_id = None
    try:
        from flask import session
        user_id = session.get("user_id")
    except Exception:
        pass

    # Xizmatni bazadan olish
    svc = db.execute(
        "SELECT * FROM services WHERE id=? AND is_active=1", (service_id,)
    ).fetchone()

    if not svc:
        return {"ok": False, "error": "Xizmat topilmadi"}

    # Narx hisoblash: price_per_1000 * quantity / 1000
    base_price  = round(svc["price_per_1000"] * quantity / 1000, 2)
    service_fee = round(base_price * 0.01, 2)
    total_price = round(base_price + service_fee, 2)

    # Balans tekshirish
    if user_id:
        user = db.execute("SELECT balance FROM users WHERE id=?", (user_id,)).fetchone()
        if not user or user["balance"] < total_price:
            return {"ok": False, "error": "Balans yetarli emas"}

    # Providega yuborish
    r = _call("add", {"service": service_id, "link": link, "quantity": quantity})

    if "order" not in r:                              # ✅ "order" - to'g'ri field
        return {"ok": False, "error": r.get("error", "Provider xatosi")}

    provider_order_id = r["order"]

    # Balansdan ayirish
    if user_id:
        db.execute(
            "UPDATE users SET balance=balance-?, total_spent=total_spent+?, total_orders=total_orders+1 WHERE id=?",
            (total_price, total_price, user_id)
        )

    # Orderni bazaga saqlash
    cur = db.execute("""
        INSERT INTO orders (user_id, service_id, provider_order_id, link, quantity, price, status)
        VALUES (?, ?, ?, ?, ?, ?, 'Pending')
    """, (user_id, service_id, provider_order_id, link, quantity, total_price))

    db.commit()

    return {"ok": True, "order_id": cur.lastrowid, "total_price": total_price}


# place_order alias
place_order = create_order


# ─── Buyurtma holati ─────────────────────────────────────────────────────────
def get_order_status(order_id):
    r = _call("status", {"order": order_id})         # ✅ "order"
    return {
        "status":      r.get("status", "Unknown"),
        "start_count": r.get("start_count", 0),
        "remains":     r.get("remains", 0),
        "charge":      r.get("charge", 0),
    }


def get_orders_status(order_ids: list):
    ids = ",".join(str(i) for i in order_ids)
    return _call("status", {"orders": ids})          # ✅ "orders"


# ─── Refill ──────────────────────────────────────────────────────────────────
def refill_order(order_id):
    r = _call("refill", {"order": order_id})         # ✅ "order"
    return r.get("refill")


def multi_refill_order(order_ids: list):
    ids = ",".join(str(i) for i in order_ids)
    return _call("refill", {"orders": ids})          # ✅ "orders"


# ─── Bekor qilish ────────────────────────────────────────────────────────────
def cancel_order(order_ids: list):
    ids = ",".join(str(i) for i in order_ids)
    return _call("cancel", {"orders": ids})          # ✅ "orders"


# ─── Auto-sync ───────────────────────────────────────────────────────────────
def sync_all_active():
    """Barcha active orderlarni provider bilan sinxron qiladi"""
    db = get_db()
    active_orders = db.execute(
        "SELECT * FROM orders WHERE status IN ('Pending', 'Processing')"
    ).fetchall()

    for order in active_orders:
        if not order["provider_order_id"]:
            continue
        try:
            status = get_order_status(order["provider_order_id"])
            db.execute(
                "UPDATE orders SET status=?, remains=?, start_count=?, updated_at=datetime('now') WHERE id=?",
                (status["status"], status["remains"], status["start_count"], order["id"])
            )
        except Exception as e:
            log.error("Sync xato order #%s: %s", order["id"], e)

    db.commit()