from functools import wraps
from flask import Blueprint, current_app, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

auth_bp = Blueprint("auth", __name__)

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped

def configured_hash():
    value = current_app.config["ADMIN_PASSWORD"]
    if value.startswith(("scrypt:", "pbkdf2:")):
        return value
    return generate_password_hash(value)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if (
            username == current_app.config["ADMIN_USERNAME"]
            and check_password_hash(configured_hash(), password)
        ):
            session.clear()
            session["admin"] = True
            return redirect(url_for("users.index"))
        error = "نام کاربری یا رمز عبور اشتباه است."
    return render_template("login.html", error=error)

@auth_bp.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
