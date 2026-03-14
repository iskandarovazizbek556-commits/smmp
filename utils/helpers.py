from flask import jsonify

def ok(data=None, msg="OK", code=200, **kw):
    r = {"ok": True, "message": msg}
    if data is not None: r["data"] = data
    r.update(kw)
    return jsonify(r), code

def er(msg="Xatolik", code=400):
    return jsonify({"ok": False, "message": msg}), code

def calc_price(price_per_1000, quantity, margin_pct):
    base  = (price_per_1000 / 1000) * quantity
    return round(base * (1 + margin_pct / 100), 2)