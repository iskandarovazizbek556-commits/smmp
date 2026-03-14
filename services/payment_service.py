import json, hashlib, sqlite3, threading
from config import Config
from utils.logger import log

def _confirm_deposit(deposit_id, user_id, amount, tx_ref=""):
    with sqlite3.connect(Config.DB_PATH) as db:
        db.execute("UPDATE deposits SET status='completed', confirmed_at=datetime('now'), external_id=? WHERE id=?",
                   (tx_ref, deposit_id))
        db.execute("UPDATE users SET balance=balance+? WHERE id=?", (amount, user_id))
        db.execute("INSERT INTO transactions (user_id,type,amount,description,ref_id) VALUES (?,?,?,?,?)",
                   (user_id, "credit", amount, f"Balans to'ldirildi ({tx_ref[:20] if tx_ref else 'manual'})", tx_ref))
        db.commit()
    log.info("Deposit confirmed: user=%s amount=%s", user_id, amount)

# ── PAYME ──────────────────────────────────────
def payme_create(deposit_id, amount_uzs, description="Balans to'ldirish"):
    """Payme to'lov havolasi yaratish"""
    if not Config.PAYME_ID:
        return {"ok": True, "url": f"#payme-demo?dep={deposit_id}&amt={amount_uzs}"}
    import base64
    amount_tiyin = amount_uzs * 100   # Payme tiyinda ishlaydi
    params = f'm={Config.PAYME_ID};ac.deposit_id={deposit_id};a={amount_tiyin}'
    encoded = base64.b64encode(params.encode()).decode()
    return {"ok": True, "url": f"{Config.PAYME_URL}/{encoded}"}

def payme_webhook(data: dict):
    """Payme server xabari"""
    method = data.get("method")
    params = data.get("params", {})

    if method == "CheckTransaction":
        dep_id = params.get("account", {}).get("deposit_id")
        return {"jsonrpc": "2.0", "result": {"allow": True}}

    if method == "CreateTransaction":
        return {"jsonrpc": "2.0", "result": {"create_time": 0, "transaction": "1", "state": 1}}

    if method == "PerformTransaction":
        dep_id = params.get("account", {}).get("deposit_id")
        amount = params.get("amount", 0) // 100
        if dep_id:
            with sqlite3.connect(Config.DB_PATH) as db:
                dep = db.execute("SELECT * FROM deposits WHERE id=?", (dep_id,)).fetchone()
                if dep:
                    _confirm_deposit(dep_id, dep["user_id"], amount, params.get("id",""))
        return {"jsonrpc": "2.0", "result": {"transaction": "1", "perform_time": 0, "state": 2}}

    return {"jsonrpc": "2.0", "result": {}}

# ── CLICK ──────────────────────────────────────
def click_prepare(data: dict):
    """Click prepare"""
    dep_id = data.get("merchant_trans_id")
    amount = float(data.get("amount", 0))
    sign_str = (f"{data.get('click_trans_id')}{data.get('service_id')}"
                f"{Config.CLICK_KEY}{dep_id}{data.get('amount')}{data.get('action')}{data.get('sign_time')}")
    sign = hashlib.md5(sign_str.encode()).hexdigest()
    if sign != data.get("sign_string"):
        return {"error": -1, "error_note": "Sign xato"}
    return {"click_trans_id": data.get("click_trans_id"),
            "merchant_trans_id": dep_id,
            "merchant_prepare_id": dep_id,
            "error": 0, "error_note": "OK"}

def click_complete(data: dict):
    """Click complete — to'lov tasdiqlandi"""
    dep_id = data.get("merchant_trans_id")
    error  = int(data.get("error", 0))
    if error < 0:
        return {"error": error, "error_note": "To'lov bekor qilindi"}
    amount = float(data.get("amount", 0))
    with sqlite3.connect(Config.DB_PATH) as db:
        dep = db.execute("SELECT * FROM deposits WHERE id=?", (dep_id,)).fetchone()
        if dep and dep["status"] == "pending":
            _confirm_deposit(dep_id, dep["user_id"], amount, str(data.get("click_trans_id","")))
    return {"click_trans_id": data.get("click_trans_id"),
            "merchant_trans_id": dep_id,
            "merchant_confirm_id": dep_id,
            "error": 0, "error_note": "OK"}

# ── USDT TRC-20 ────────────────────────────────
def usdt_rate_uzs():
    try:
        import urllib.request
        r = json.loads(urllib.request.urlopen(
            "https://api.binance.com/api/v3/ticker/price?symbol=USDTUZS", timeout=5).read())
        return float(r["price"])
    except: return 12700.0

def usdt_create(deposit_id, amount_uzs):
    if not Config.USDT_WALLET:
        return {"ok": False, "message": "USDT sozlanmagan"}
    rate = usdt_rate_uzs()
    amt  = round(amount_uzs / rate, 2)
    return {"ok": True, "wallet": Config.USDT_WALLET, "network": "TRC-20",
            "amount_usdt": amt, "amount_uzs": amount_uzs, "rate": rate}

def usdt_check(deposit_id, user_id, amount_uzs, amount_usd, wallet, created_at, tx_hash=""):
    if Config.TRONGRID_KEY:
        try:
            import urllib.request
            from datetime import datetime
            USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
            url  = (f"https://api.trongrid.io/v1/accounts/{wallet}/transactions/trc20"
                    f"?contract_address={USDT_CONTRACT}&limit=10&order_by=block_timestamp,desc")
            req  = urllib.request.Request(url, headers={"TRON-PRO-API-KEY": Config.TRONGRID_KEY})
            resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
            from_ts = int(datetime.fromisoformat(created_at).timestamp() * 1000)
            for tx in resp.get("data", []):
                if tx.get("to") != wallet: continue
                if tx.get("block_timestamp", 0) < from_ts: continue
                val = int(tx.get("value",0)) / 1_000_000
                if abs(val - amount_usd) < 0.05:
                    _confirm_deposit(deposit_id, user_id, amount_uzs, tx["transaction_id"])
                    return {"ok": True, "confirmed": True}
            return {"ok": True, "confirmed": False}
        except Exception as e:
            log.error("USDT check: %s", e)
    # Qo'lda tx hash bilan
    if tx_hash:
        _confirm_deposit(deposit_id, user_id, amount_uzs, tx_hash)
        return {"ok": True, "confirmed": True, "manual": True}
    return {"ok": True, "confirmed": False}