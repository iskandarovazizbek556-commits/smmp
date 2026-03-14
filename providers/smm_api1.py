# providers/smm_api1.py

import json, urllib.request, urllib.parse
from config import Config
from utils.logger import log

API_URL = Config.PROVIDER_URL
API_KEY = Config.PROVIDER_KEY


# ─── Ichki so'rov ─────────────────────────────────────────────────────────────
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


# ─── Provider balans ──────────────────────────────────────────────────────────
def get_balance():
    r = _call("balance")
    return r.get("balance", 0)


# ─── Yangi order ─────────────────────────────────────────────────────────────
def create_order(service_id, link, quantity):
    r = _call("add", {"service": service_id, "link": link, "quantity": quantity})
    if "order" in r:
        return {"ok": True, "order_id": r["order"]}
    return {"ok": False, "error": r.get("error", "Noma'lum xato")}


# ─── Order holati ─────────────────────────────────────────────────────────────
def get_order_status(order_id):
    r = _call("status", {"order": order_id})
    return {
        "status":      r.get("status", "Unknown"),
        "start_count": r.get("start_count", 0),
        "remains":     r.get("remains", 0),
        "charge":      r.get("charge", 0),
    }


def get_orders_status(order_ids: list):
    ids = ",".join(str(i) for i in order_ids)
    return _call("status", {"orders": ids})


# ─── Refill ───────────────────────────────────────────────────────────────────
def refill_order(order_id):
    r = _call("refill", {"order": order_id})
    return r.get("refill")


def multi_refill_order(order_ids: list):
    ids = ",".join(str(i) for i in order_ids)
    return _call("refill", {"orders": ids})


# ─── Bekor qilish ─────────────────────────────────────────────────────────────
def cancel_order(order_ids: list):
    ids = ",".join(str(i) for i in order_ids)
    return _call("cancel", {"orders": ids})


def get_services():
    """Barcha xizmatlarni providerdan olish"""
    return _call("services")