import sqlite3, hashlib, secrets
from config import Config
from database.models import SCHEMA, SEED

def init_db():
    with sqlite3.connect(Config.DB_PATH) as db:
        db.executescript(SCHEMA)
        db.executescript(SEED)

        # Admin user
        pw  = hashlib.sha256(Config.ADMIN_PASS.encode()).hexdigest()
        key = secrets.token_hex(16)
        rc  = secrets.token_hex(4).upper()
        db.execute(
            "INSERT OR IGNORE INTO users (username,email,password,role,api_key,ref_code) VALUES (?,?,?,?,?,?)",
            (Config.ADMIN_USER, Config.ADMIN_EMAIL, pw, "admin", key, rc)
        )
        db.commit()
    print(f"[DB] Tayyor: {Config.DB_PATH}")

if __name__ == "__main__":
    init_db()