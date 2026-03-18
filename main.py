import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, redirect, url_for, session
from config import Config
from database.db import get_db, close_db
from database.migrate import init_db
from utils.logger import log

# ─── App ──────────────────────────────────────
app = Flask(__name__,
            template_folder="templates",
            static_folder="static")
app.secret_key = Config.SECRET_KEY
app.config["SESSION_COOKIE_HTTPONLY"]  = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

from datetime import timedelta
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

# ─── DB teardown ──────────────────────────────
app.teardown_appcontext(close_db)

# ─── Blueprints ───────────────────────────────
from auth.login               import auth_bp
from services.user_service    import user_bp
from services.admin_service   import admin_bp
from api.routes               import api_bp
from support_service          import support_bp
from services.payment_service import payme_webhook, click_prepare, click_complete

app.register_blueprint(auth_bp)
app.register_blueprint(user_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(api_bp)
app.register_blueprint(support_bp)

# ─── Payment webhooks ─────────────────────────
from flask import request, jsonify, render_template

@app.route("/api/webhook/payme", methods=["POST"])
def payme_wh():
    return jsonify(payme_webhook(request.get_json() or {}))

@app.route("/api/webhook/click/prepare", methods=["POST"])
def click_prep():
    return jsonify(click_prepare(request.form.to_dict()))

@app.route("/api/webhook/click/complete", methods=["POST"])
def click_comp():
    return jsonify(click_complete(request.form.to_dict()))

# ─── Root ─────────────────────────────────────
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("user.dashboard"))
    return render_template("index.html")

# ─── Context processor ────────────────────────
@app.context_processor
def inject_globals():
    user_balance = 0
    if "user_id" in session:
        db = get_db()
        u  = db.execute("SELECT balance FROM users WHERE id=?", (session["user_id"],)).fetchone()
        if u: user_balance = u["balance"]
        session["balance"] = user_balance
    return {"site_name": Config.SITE_NAME, "user_balance": user_balance}

# ─── Error handlers ───────────────────────────
@app.errorhandler(404)
def e404(e): return render_template("index.html"), 404

@app.errorhandler(403)
def e403(e): return jsonify({"error": "Ruxsat yo'q"}), 403


# ═══════════════════════════════════════════════════════════
#  1xPanel API Client
# ═══════════════════════════════════════════════════════════
import requests as _requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ProviderApi:
    api_url: str = "https://1xpanel.com/api/v2"
    api_key: str = ""

    def __init__(self, api_url: str = None, api_key: str = None):
        if api_url:
            self.api_url = api_url
        self.api_key = api_key or getattr(Config, "PROVIDER_KEY", "")

    def _connect(self, post: dict):
        try:
            resp = _requests.post(
                self.api_url,
                data=post,
                headers={"User-Agent": "Mozilla/4.0 (compatible; MSIE 5.01; Windows NT 5.0)"},
                verify=False,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except _requests.exceptions.RequestException as e:
            log.error("ProviderApi ulanish xatosi: %s", e)
            return None
        except ValueError as e:
            log.error("ProviderApi JSON xatosi: %s", e)
            return None

    def services(self):
        return self._connect({"key": self.api_key, "action": "services"})

    def balance(self):
        return self._connect({"key": self.api_key, "action": "balance"})

    def order(self, data: dict):
        post = {"key": self.api_key, "action": "add", **data}
        return self._connect(post)

    def status(self, order_id: int):
        return self._connect({"key": self.api_key, "action": "status", "order": order_id})

    def multi_status(self, order_ids: list):
        return self._connect({"key": self.api_key, "action": "status", "orders": ",".join(map(str, order_ids))})

    def refill(self, order_id: int):
        return self._connect({"key": self.api_key, "action": "refill", "order": order_id})

    def multi_refill(self, order_ids: list):
        return self._connect({"key": self.api_key, "action": "refill", "orders": ",".join(map(str, order_ids))})

    def refill_status(self, refill_id: int):
        return self._connect({"key": self.api_key, "action": "refill_status", "refill": refill_id})

    def multi_refill_status(self, refill_ids: list):
        return self._connect({"key": self.api_key, "action": "refill_status", "refills": ",".join(map(str, refill_ids))})

    def cancel(self, order_ids: list):
        return self._connect({"key": self.api_key, "action": "cancel", "orders": ",".join(map(str, order_ids))})


provider_api = ProviderApi(
    api_url=getattr(Config, "PROVIDER_URL", "https://1xpanel.com/api/v2"),
    api_key=getattr(Config, "PROVIDER_KEY", ""),
)


# ─── Auto sync (background) ───────────────────
def start_auto_sync():
    import threading, time
    def _loop():
        while True:
            time.sleep(300)
            try:
                from services.order_service import sync_all_active
                sync_all_active()
            except Exception as e:
                log.error("Auto-sync xato: %s", e)
    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    log.info("Auto-sync ishga tushdi (har 5 daqiqa)")


# ─── Main ─────────────────────────────────────
if __name__ == "__main__":
    init_db()
    start_auto_sync()

    print("=" * 58)
    print("  📊  SMMPanel.uz — ishga tushmoqda")
    print("=" * 58)
    print(f"  🌐  Sayt:    http://localhost:{Config.PORT}")
    print(f"  🛡   Admin:   http://localhost:{Config.PORT}/admin/")
    print(f"  🔑  Login:   {Config.ADMIN_USER} / {Config.ADMIN_PASS}")
    print(f"  📡  API:     http://localhost:{Config.PORT}/api/v2")
    print("-" * 58)
    print(f"  1xPanel: {'ulangan' if Config.PROVIDER_KEY else 'YOQ — PROVIDER_KEY qoshing'}")
    print(f"  Payme:   {'ulangan' if Config.PAYME_ID else 'YOQ'}")
    print(f"  Click:   {'ulangan' if Config.CLICK_MERCHANT else 'YOQ'}")
    print(f"  USDT:    {'ulangan' if Config.USDT_WALLET else 'YOQ'}")
    print("=" * 58)

    app.run(debug=False, host="0.0.0.0", port=Config.PORT)