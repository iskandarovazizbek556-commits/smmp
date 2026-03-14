# config.py
import os, secrets

def env(k, d=""):
    return os.environ.get(k, d)

class Config:

    SECRET_KEY   = env("SECRET_KEY", secrets.token_hex(32))
    DB_PATH      = env("DB_PATH", "smm_panel.db")

    SITE_URL     = env("SITE_URL", "http://localhost:8000")
    SITE_NAME    = env("SITE_NAME", "SMMPanel.uz")

    PORT         = int(env("PORT", "8000"))

    ADMIN_USER   = env("ADMIN_USER", "admin")
    ADMIN_PASS   = env("ADMIN_PASS", "admin123")
    ADMIN_EMAIL  = env("ADMIN_EMAIL", "admin@smmpanel.uz")

    # Provider API
    PROVIDER_URL = env("PROVIDER_URL", "https://1xpanel.com/api/v2")
    PROVIDER_KEY = env("PROVIDER_KEY", "ba8e1bc47a108e16b123c7bf190eec75")

    # Payme
    PAYME_ID     = env("PAYME_ID", "")
    PAYME_KEY    = env("PAYME_KEY", "")
    PAYME_URL    = "https://checkout.paycom.uz"

    # Click
    CLICK_MERCHANT = env("CLICK_MERCHANT", "")
    CLICK_SERVICE  = env("CLICK_SERVICE", "")
    CLICK_KEY      = env("CLICK_KEY", "")

    # USDT
    USDT_WALLET  = env("USDT_WALLET", "")
    TRONGRID_KEY = env("TRONGRID_KEY", "")

    # ✅ Telegram bot
    TG_TOKEN     = env("TG_BOT_TOKEN", "8524574712:AAGAL1UTGx84ggiap1SAdp57s_dc7MyRXu8")
    TG_ADMIN     = env("TG_ADMIN_CHAT_ID", "7721593413")

    # ✅ Karta raqam
    CARD_NUMBER  = env("CARD_NUMBER", "9860 0000 0000 8600")

    # Minimal depozit
    MIN_DEPOSIT  = 5000

    # Foyda %
    MARGIN       = float(env("MARGIN", "100"))