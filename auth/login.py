from flask import Blueprint, request, session, redirect, url_for, render_template, flash
from database.db import get_db, execute
from utils.security import hash_pw, check_pw, gen_key, gen_ref
from datetime import timedelta
import secrets

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET","POST"])
def login_page():
    if "user_id" in session:
        return redirect(url_for("user.dashboard"))
    if request.method == "POST":
        login = request.form.get("login","").strip()
        pw    = request.form.get("password","")
        db    = get_db()
        u     = db.execute(
            "SELECT * FROM users WHERE email=? OR username=?", (login, login)
        ).fetchone()
        if not u or not check_pw(pw, u["password"]):
            flash("Login yoki parol noto'g'ri", "error")
            return redirect(url_for("auth.login_page"))
        if not u["is_active"]:
            flash("Akkaunt bloklangan", "error")
            return redirect(url_for("auth.login_page"))
        session.permanent = True
        session["user_id"]  = u["id"]
        session["username"] = u["username"]
        session["role"]     = u["role"]
        if u["role"] == "admin":
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("user.dashboard"))
    return render_template("login.html")

@auth_bp.route("/register", methods=["GET","POST"])
def register_page():
    if "user_id" in session:
        return redirect(url_for("user.dashboard"))
    if request.method == "POST":
        username = request.form.get("username","").strip()
        email    = request.form.get("email","").strip().lower()
        pw       = request.form.get("password","")
        pw2      = request.form.get("password2","")
        ref_code = request.form.get("ref","").strip().upper()

        if not username or not email or not pw:
            flash("Barcha maydonlar to'ldirilishi shart", "error")
            return redirect(url_for("auth.register_page"))
        if len(pw) < 8:
            flash("Parol kamida 8 ta belgi", "error")
            return redirect(url_for("auth.register_page"))
        if pw != pw2:
            flash("Parollar mos kelmadi", "error")
            return redirect(url_for("auth.register_page"))

        db = get_db()
        if db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
            flash("Bu username band", "error")
            return redirect(url_for("auth.register_page"))
        if db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
            flash("Bu email ro'yxatdan o'tgan", "error")
            return redirect(url_for("auth.register_page"))

        ref_by = None
        if ref_code:
            ru = db.execute("SELECT id FROM users WHERE ref_code=?", (ref_code,)).fetchone()
            if ru: ref_by = ru["id"]

        # Ro'yxatdan o'tish bonusi
        bonus = float(db.execute("SELECT value FROM settings WHERE key='reg_bonus'").fetchone()["value"] or 0)

        api_key = gen_key()
        my_ref  = gen_ref()
        db.execute(
            "INSERT INTO users (username,email,password,api_key,ref_code,referred_by,balance) VALUES (?,?,?,?,?,?,?)",
            (username, email, hash_pw(pw), api_key, my_ref, ref_by, bonus)
        )
        db.commit()
        u = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if bonus > 0:
            db.execute("INSERT INTO transactions (user_id,type,amount,description) VALUES (?,?,?,?)",
                       (u["id"], "credit", bonus, "Ro'yxatdan o'tish bonusi"))
            db.commit()

        session.permanent = True
        session["user_id"]  = u["id"]
        session["username"] = u["username"]
        session["role"]     = u["role"]
        return redirect(url_for("user.dashboard"))
    return render_template("register.html")

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login_page"))