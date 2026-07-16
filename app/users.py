import subprocess
from io import BytesIO

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for

from .auth import login_required
from .db import connect
from .linux_users import create_or_update, delete as delete_linux, pause as pause_linux, resume as resume_linux
from .ports import allocate
from .security import validate_csrf

users_bp = Blueprint("users", __name__)

def get_user(username):
    with connect() as c:
        row = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    return dict(row) if row else None

def human_bytes(value):
    value = int(value or 0)
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024

def list_users():
    with connect() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM users ORDER BY id DESC")]
    for user in rows:
        user["used_bytes"] = int(user["rx_bytes"] or 0) + int(user["tx_bytes"] or 0)
        user["used_human"] = human_bytes(user["used_bytes"])
        user["limit_gb"] = int(user["limit_bytes"] or 0) / (1024**3)
        user["percent"] = min(
            100,
            (user["used_bytes"] / user["limit_bytes"] * 100)
            if int(user["limit_bytes"] or 0) > 0 else 0,
        )
    return rows

def restart_proxy():
    result = subprocess.run(
        ["systemctl", "restart", "custom-panel-proxy"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=30, check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "راه‌اندازی Proxy ناموفق بود.")

@users_bp.get("/")
@login_required
def index():
    return render_template("index.html", users=list_users())

@users_bp.post("/users")
@login_required
def add():
    validate_csrf()
    try:
        username = request.form["username"].strip()
        password = request.form["password"]
        limit_gb = float(request.form["limit_gb"])
        remaining_days = int(request.form["remaining_days"])
        if limit_gb < 0 or remaining_days < 1:
            raise ValueError("حجم یا زمان باقی‌مانده نامعتبر است.")
        if get_user(username):
            raise ValueError("این نام کاربری قبلاً وجود دارد.")

        create_or_update(username, password)
        port = allocate()

        with connect() as c:
            c.execute("""
            INSERT INTO users(
              username,password,port,limit_bytes,remaining_days
            ) VALUES(?,?,?,?,?)
            """, (
                username, password, port,
                int(limit_gb * (1024**3)), remaining_days,
            ))
            c.commit()

        restart_proxy()
        flash("کاربر با موفقیت ساخته شد.", "success")
    except Exception as exc:
        flash(f"خطا: {exc}", "error")
    return redirect(url_for("users.index"))

@users_bp.post("/users/<username>/edit")
@login_required
def edit(username):
    validate_csrf()
    user = get_user(username)
    if not user:
        return redirect(url_for("users.index"))
    try:
        password = request.form.get("password") or user["password"]
        limit_gb = float(request.form.get("limit_gb", int(user["limit_bytes"])/(1024**3)))
        remaining_days = int(request.form.get("remaining_days", user["remaining_days"]))
        if limit_gb < 0 or remaining_days < 0:
            raise ValueError("مقادیر ویرایش نامعتبر هستند.")

        create_or_update(username, password)
        with connect() as c:
            c.execute("""
            UPDATE users
            SET password=?,limit_bytes=?,remaining_days=?,
                status=CASE WHEN paused=0 AND ?>0 THEN 'Active' ELSE status END,
                updated_at=CURRENT_TIMESTAMP
            WHERE username=?
            """, (
                password, int(limit_gb*(1024**3)), remaining_days,
                remaining_days, username,
            ))
            c.commit()

        restart_proxy()
        flash("تغییرات ذخیره شد.", "success")
    except Exception as exc:
        flash(f"خطا: {exc}", "error")
    return redirect(url_for("users.index"))

@users_bp.post("/users/<username>/<action>")
@login_required
def action(username, action):
    validate_csrf()
    user = get_user(username)
    if not user:
        return redirect(url_for("users.index"))
    try:
        if action == "pause":
            pause_linux(username)
            with connect() as c:
                c.execute("UPDATE users SET paused=1,status='Paused',online=0 WHERE username=?", (username,))
                c.commit()
            restart_proxy()
        elif action == "resume":
            if int(user["remaining_days"]) <= 0:
                raise ValueError("ابتدا زمان باقی‌مانده را افزایش بده.")
            resume_linux(username)
            with connect() as c:
                c.execute("UPDATE users SET paused=0,status='Active' WHERE username=?", (username,))
                c.commit()
            restart_proxy()
        elif action == "reset-traffic":
            with connect() as c:
                c.execute("UPDATE users SET rx_bytes=0,tx_bytes=0 WHERE username=?", (username,))
                c.commit()
        elif action == "delete":
            delete_linux(username)
            with connect() as c:
                c.execute("DELETE FROM users WHERE username=?", (username,))
                c.commit()
            restart_proxy()
        flash("عملیات انجام شد.", "success")
    except Exception as exc:
        flash(f"خطا: {exc}", "error")
    return redirect(url_for("users.index"))

@users_bp.get("/users/<username>/config")
@login_required
def config(username):
    user = get_user(username)
    if not user:
        return ("Not found", 404)
    content = (
        f"Server: {current_app.config['SERVER_HOST']}\n"
        f"Port: {user['port']}\n"
        f"Username: {user['username']}\n"
        f"Password: {user['password']}\n"
        f"Remaining days: {user['remaining_days']}\n"
    )
    return send_file(
        BytesIO(content.encode()),
        as_attachment=True,
        download_name=f"{username}-ssh.txt",
        mimetype="text/plain",
    )
