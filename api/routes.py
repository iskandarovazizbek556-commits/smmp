# app/api/routes.py

import requests
from flask import Blueprint, jsonify
from config import Config
from database.db import get_db

api_bp = Blueprint("import_api", __name__, url_prefix="/api/v2")

CURRENCY_RATE = 12500  # 1 USD = 12500 so'm
MARKUP = 1.04          # 4% ustama


def fetch_1xpanel_services():
    url = f"{Config.PROVIDER_URL}?action=services&key={Config.PROVIDER_KEY}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        return {"error": f"API bilan bog'lanishda xato: {e}"}

    if not isinstance(data, list):
        return {"error": "API noto'g'ri format qaytardi"}

    services = []
    for s in data:
        raw_rate = float(s.get("rate", 0))
        price_per_1000_uzs = round(raw_rate * CURRENCY_RATE * MARKUP, 2)

        services.append({
            "service_id":     int(s.get("service", 0)),
            "name":           s.get("name", ""),
            "category":       s.get("category", "General"),
            "type":           s.get("type", ""),
            "price_per_1000": price_per_1000_uzs,
            "min":            int(s.get("min", 0)),
            "max":            int(s.get("max", 0)),
            "description":    s.get("description", "")
        })
    return services


@api_bp.route("/import-services", methods=["POST"])
def import_services():
    db = get_db()
    services = fetch_1xpanel_services()

    if isinstance(services, dict) and "error" in services:
        return jsonify(services), 400

    imported = 0
    for s in services:
        category_id = get_category_id(db, s["category"])
        db.execute("""
            INSERT OR REPLACE INTO services
            (id, name, category_id, type, price_per_1000, min_order, max_order, description, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            s["service_id"],
            s["name"],
            category_id,
            s["type"],
            s["price_per_1000"],  # ✅ so'mda, 4% ustama bilan
            s["min"],
            s["max"],
            s["description"]
        ))
        imported += 1

    db.commit()
    return jsonify({"ok": True, "imported": imported})


def get_category_id(db, cat_name):
    if not cat_name:
        cat_name = "General"
    row = db.execute(
        "SELECT id FROM categories WHERE name=?", (cat_name,)
    ).fetchone()
    if row:
        return row["id"]
    cur = db.execute(
        "INSERT INTO categories (name) VALUES (?)", (cat_name,)
    )
    db.commit()
    return cur.lastrowid