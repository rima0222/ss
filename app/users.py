import datetime as dt
import secrets
from io import BytesIO

from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for, current_app

from .auth import login_required
from .db import connect
from .linux_users import create_or_update, pause as pause_linux, resume as resume_linux, delete as delete_linux
from .ports import allocate
from .security import validate_csrf

users_bp = Blueprint("users", __name__)

def get_user(username):
    with connect() as c:
        row = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    return dict(row) if row else None

def list_users():
    today = dt.date.today()
    with connect() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM users ORDER BY id DESC")]
        details = {
            r["user_id"]: []
            for r in c.execute("SELECT user_id FROM proxy_counters GROUP BY user_id")
        }
        for r in c.execute("SELECT * FROM proxy_counters"):
            details.setdefault(r["user_id"], []).append(dict(r))

    for u in rows:
        try:
            u["remaining_days"] = max(0, (dt.date.fromisoformat(u["expire_date"]) - today).days)
        except Exception:
            u["remaining_days"] = 0
        u["used_gb"] = (int(u["rx_bytes"] or 0) + int(u["tx_bytes"] or 0)) / (1024**3)
        u["transport_stats"] = details.get(u["id"], [])
    return rows

def restart_proxy():
    import subprocess
    subprocess.run(["systemctl", "restart", "custom-panel-proxy"], check=False)

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
        days = int(request.form["days"])
        selected = set(request.form.getlist("protocols"))
        if not selected:
            raise ValueError("حداقل یک روش اتصال انتخاب کن.")
        if get_user(username):
            raise ValueError("این نام کاربری قبلاً وجود دارد.")

        create_or_update(username, password)

        values = {
            "openssh_enabled": int("openssh" in selected),
            "dropbear_enabled": int("dropbear" in selected),
            "ws_enabled": int("ws" in selected),
            "tls_enabled": int("tls" in selected),
            "openssh_port": allocate("openssh_port", "openssh") if "openssh" in selected else None,
            "dropbear_port": allocate("dropbear_port", "dropbear") if "dropbear" in selected else None,
            "ws_port": allocate("ws_port", "ws") if "ws" in selected else None,
            "tls_port": allocate("tls_port", "tls") if "tls" in selected else None,
            "ws_token": secrets.token_urlsafe(18) if "ws" in selected else None,
        }

        expire = (dt.date.today() + dt.timedelta(days=days)).isoformat()
        with connect() as c:
            c.execute("""
            INSERT INTO users(
              username,password,limit_gb,expire_date,
              openssh_enabled,dropbear_enabled,ws_enabled,tls_enabled,
              openssh_port,dropbear_port,ws_port,tls_port,ws_token
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                username,password,limit_gb,expire,
                values["openssh_enabled"],values["dropbear_enabled"],
                values["ws_enabled"],values["tls_enabled"],
                values["openssh_port"],values["dropbear_port"],
                values["ws_port"],values["tls_port"],values["ws_token"],
            ))
            c.commit()

        restart_proxy()
        flash("کاربر ساخته شد.", "success")
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
        limit_gb = float(request.form.get("limit_gb", user["limit_gb"]))
        remaining = request.form.get("remaining_days")
        expire = user["expire_date"]
        if remaining not in (None, ""):
            expire = (dt.date.today() + dt.timedelta(days=int(remaining))).isoformat()

        create_or_update(username, password)
        with connect() as c:
            c.execute("""
            UPDATE users
            SET password=?,limit_gb=?,expire_date=?,updated_at=CURRENT_TIMESTAMP
            WHERE username=?
            """, (password,limit_gb,expire,username))
            c.commit()
        flash("ویرایش ذخیره شد.", "success")
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
                c.execute("UPDATE users SET paused=1,status='Paused' WHERE username=?", (username,))
                c.commit()
            restart_proxy()
        elif action == "resume":
            resume_linux(username)
            with connect() as c:
                c.execute("UPDATE users SET paused=0,status='Active' WHERE username=?", (username,))
                c.commit()
            restart_proxy()
        elif action == "reset-traffic":
            with connect() as c:
                c.execute("DELETE FROM proxy_counters WHERE user_id=?", (user["id"],))
                c.execute("UPDATE users SET rx_bytes=0,tx_bytes=0 WHERE id=?", (user["id"],))
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
        return ("Not found",404)

    host = current_app.config["SERVER_HOST"]
    lines = [
        f"Username: {user['username']}",
        f"Password: {user['password']}",
        "",
    ]
    if user["openssh_enabled"]:
        lines += ["OpenSSH:", f"Host: {host}", f"Port: {user['openssh_port']}", ""]
    if user["dropbear_enabled"]:
        lines += ["Dropbear:", f"Host: {host}", f"Port: {user['dropbear_port']}", ""]
    if user["ws_enabled"]:
        lines += [
            "SSH WebSocket:",
            f"URL: ws://{host}:{user['ws_port']}/ws/{user['ws_token']}",
            "Backend: OpenSSH",
            "",
        ]
    if user["tls_enabled"]:
        lines += [
            "SSH TLS:",
            f"Host: {host}",
            f"Port: {user['tls_port']}",
            "Use a TLS/stunnel client.",
            "",
        ]

    data = "\n".join(lines).encode()
    return send_file(
        BytesIO(data),
        as_attachment=True,
        download_name=f"{username}-ssh-suite.txt",
        mimetype="text/plain",
    )
