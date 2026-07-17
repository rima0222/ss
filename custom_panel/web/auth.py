import time
from collections import defaultdict, deque

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from ..db import connect
from ..settings import settings
from .common import csrf_token

auth_bp = Blueprint("auth", __name__)
_attempts = defaultdict(deque)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    client = request.remote_addr or "unknown"
    now = time.time()
    queue = _attempts[client]
    while queue and now - queue[0] > 300:
        queue.popleft()

    if request.method == "POST":
        if len(queue) >= 8:
            return render_template("login.html", error="تلاش ورود بیش از حد است."), 429
        with connect(settings.db_path) as conn:
            admin = conn.execute(
                "SELECT username,password_hash,session_version FROM admins WHERE id=1"
            ).fetchone()
        if admin and request.form.get("username") == admin["username"] and check_password_hash(
            admin["password_hash"], request.form.get("password", "")
        ):
            queue.clear()
            session.clear()
            session["admin"] = True
            session["session_version"] = admin["session_version"]
            return redirect(url_for("panel.dashboard"))
        queue.append(now)
        error = "نام کاربری یا رمز عبور اشتباه است."
    return render_template("login.html", error=error, csrf_token=csrf_token)

@auth_bp.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
