import time
from collections import defaultdict, deque
from functools import wraps

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

auth_bp = Blueprint("auth", __name__)
_ATTEMPTS = defaultdict(deque)
WINDOW = 300
MAX_ATTEMPTS = 8

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped

def client_key():
    return request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()

def limited(key):
    now = time.time()
    q = _ATTEMPTS[key]
    while q and now - q[0] > WINDOW:
        q.popleft()
    return len(q) >= MAX_ATTEMPTS

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    key = client_key()
    if request.method == "POST":
        if limited(key):
            return render_template("login.html", error="تلاش ورود بیش از حد است. چند دقیقه بعد دوباره امتحان کن."), 429
        valid = (
            request.form.get("username") == current_app.config["ADMIN_USERNAME"]
            and check_password_hash(
                current_app.config["ADMIN_PASSWORD_HASH"],
                request.form.get("password", ""),
            )
        )
        if valid:
            _ATTEMPTS.pop(key, None)
            session.clear()
            session["admin"] = True
            return redirect(url_for("users.index"))
        _ATTEMPTS[key].append(time.time())
        error = "نام کاربری یا رمز عبور اشتباه است."
    return render_template("login.html", error=error)

@auth_bp.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
