# app/api/order_api.py

from flask import Blueprint, request, jsonify, session
from database.db import get_db
from providers.smm_api1 import create_order as provider_create_order
from utils.logger import log

order_bp = Blueprint("order_api", __name__, url_prefix="/api/v2")


# ─── Xizmatlar ro'yxati ───────────────────────────────────────────────────────
@order_bp.route("/services", methods=["GET"])
def get_services():
    """Barcha aktiv xizmatlarni qaytaradi (narx allaqachon so'mda, 4% bilan)"""
    db = get_db()
    rows = db.execute("""
        SELECT s.id, s.name, s.type, s.price_per_1000,
               s.min_order, s.max_order, s.description,
               c.name AS category
        FROM services s
        JOIN categories c ON s.category_id = c.id
        WHERE s.is_active = 1
        ORDER BY c.sort_order, s.id
    """).fetchall()

    services = []
    for r in rows:
        services.append({
            "id":            r["id"],
            "name":          r["name"],
            "category":      r["category"],
            "type":          r["type"],
            "price_per_1000": r["price_per_1000"],  # so'mda
            "min":           r["min_order"],
            "max":           r["max_order"],
            "description":   r["description"] or ""
        })

    return jsonify(services)


# ─── Narx hisoblash ───────────────────────────────────────────────────────────
@order_bp.route("/calculate-price", methods=["POST"])
def calculate_price():
    """Frontend uchun: service_id + quantity -> narx"""
    data = request.get_json() or {}
    service_id = data.get("service_id")
    quantity   = int(data.get("quantity", 0))

    if not service_id or quantity <= 0:
        return jsonify({"error": "service_id va quantity kerak"}), 400

    db = get_db()
    service = db.execute(
        "SELECT price_per_1000, min_order, max_order FROM services WHERE id=? AND is_active=1",
        (service_id,)
    ).fetchone()

    if not service:
        return jsonify({"error": "Xizmat topilmadi"}), 404

    if quantity < service["min_order"] or quantity > service["max_order"]:
        return jsonify({
            "error": f"Miqdor {service['min_order']} - {service['max_order']} orasida bo'lishi kerak"
        }), 400

    # Narx hisoblash: price_per_1000 * quantity / 1000
    base_price    = round(service["price_per_1000"] * quantity / 1000, 2)
    service_fee   = round(base_price * 0.01, 2)   # 1% xizmat to'lovi
    total_price   = round(base_price + service_fee, 2)

    return jsonify({
        "base_price":  base_price,
        "service_fee": service_fee,
        "total":       total_price
    })


# ─── Yangi order yaratish ─────────────────────────────────────────────────────
@order_bp.route("/order", methods=["POST"])
def create_order():
    """Yangi buyurtma yaratish"""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Login qiling"}), 401

    data       = request.get_json() or {}
    service_id = data.get("service_id")
    link       = data.get("link", "").strip()
    quantity   = int(data.get("quantity", 0))

    if not service_id or not link or quantity <= 0:
        return jsonify({"error": "service_id, link va quantity kerak"}), 400

    db = get_db()

    # Xizmatni tekshirish
    service = db.execute(
        "SELECT * FROM services WHERE id=? AND is_active=1", (service_id,)
    ).fetchone()

    if not service:
        return jsonify({"error": "Xizmat topilmadi"}), 404

    if quantity < service["min_order"] or quantity > service["max_order"]:
        return jsonify({
            "error": f"Miqdor {service['min_order']} - {service['max_order']} orasida bo'lishi kerak"
        }), 400

    # Narx hisoblash
    base_price  = round(service["price_per_1000"] * quantity / 1000, 2)
    service_fee = round(base_price * 0.01, 2)
    total_price = round(base_price + service_fee, 2)

    # Foydalanuvchi balansini tekshirish
    user = db.execute("SELECT balance FROM users WHERE id=?", (user_id,)).fetchone()
    if not user or user["balance"] < total_price:
        return jsonify({"error": "Balans yetarli emas"}), 400

    # Provider ga order yuborish
    result = provider_create_order(service_id, link, quantity)
    if not result.get("ok"):
        log.error("Provider order xato: %s", result.get("error"))
        return jsonify({"error": result.get("error", "Provider xatosi")}), 500

    provider_order_id = result.get("order_id")

    # Balansdan ayirish
    db.execute(
        "UPDATE users SET balance = balance - ?, total_spent = total_spent + ?, total_orders = total_orders + 1 WHERE id=?",
        (total_price, total_price, user_id)
    )

    # Orderni bazaga saqlash
    cur = db.execute("""
        INSERT INTO orders (user_id, service_id, provider_order_id, link, quantity, price, status)
        VALUES (?, ?, ?, ?, ?, ?, 'Pending')
    """, (user_id, service_id, provider_order_id, link, quantity, total_price))

    # Tranzaksiya yozish
    db.execute("""
        INSERT INTO transactions (user_id, type, amount, description, ref_id)
        VALUES (?, 'order', ?, ?, ?)
    """, (user_id, -total_price, f"Order #{cur.lastrowid} - {service['name']}", str(cur.lastrowid)))

    db.commit()

    return jsonify({
        "ok":       True,
        "order_id": cur.lastrowid,
        "price":    total_price
    })


# ─── Order holati ─────────────────────────────────────────────────────────────
@order_bp.route("/order/<int:order_id>", methods=["GET"])
def get_order(order_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Login qiling"}), 401

    db  = get_db()
    row = db.execute("""
        SELECT o.*, s.name as service_name
        FROM orders o
        JOIN services s ON o.service_id = s.id
        WHERE o.id=? AND o.user_id=?
    """, (order_id, user_id)).fetchone()

    if not row:
        return jsonify({"error": "Order topilmadi"}), 404

    return jsonify({
        "id":           row["id"],
        "service":      row["service_name"],
        "link":         row["link"],
        "quantity":     row["quantity"],
        "price":        row["price"],
        "status":       row["status"],
        "start_count":  row["start_count"],
        "remains":      row["remains"],
        "created_at":   row["created_at"]
    })