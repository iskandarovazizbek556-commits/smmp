from functools import wraps
from flask import session, request, jsonify, redirect, url_for
from database.db import get_db

def login_required(f):
    @wraps(f)
    def d(*a, **kw):
        if "user_id" not in session:
            if request.is_json:
                return jsonify({"ok": False, "message": "Login kerak"}), 401
            return redirect(url_for("auth.login_page"))
        return f(*a, **kw)
    return d

def admin_required(f):
    @wraps(f)
    def d(*a, **kw):
        if "user_id" not in session:
            return redirect(url_for("auth.login_page"))
        db = get_db()
        u  = db.execute("SELECT role FROM users WHERE id=?", (session["user_id"],)).fetchone()
        if not u or u["role"] != "admin":
            return jsonify({"ok": False, "message": "Ruxsat yo'q"}), 403
        return f(*a, **kw)
    return d

def api_key_required(f):
    @wraps(f)
    def d(*a, **kw):
        key = request.form.get("key") or request.args.get("key")
        if not key:
            return jsonify({"error": "API key required"})
        db = get_db()
        u  = db.execute("SELECT * FROM users WHERE api_key=? AND is_active=1", (key,)).fetchone()
        if not u:
            return jsonify({"error": "Invalid API key"})
        from flask import g
        g.api_user = dict(u)
        return f(*a, **kw)
    return d