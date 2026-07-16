import datetime as dt
import uuid
from io import BytesIO

from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for

from .auth import login_required
from .db import connect
from .security import validate_csrf
from .system_accounts import create_or_update, delete as delete_linux, pause as pause_linux, resume as resume_linux
from .xray_manager import regenerate, vmess_uri

users_bp = Blueprint("users", __name__)

def get_user(username):
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    return dict(row) if row else None

def list_users():
    today = dt.date.today()
    with connect() as conn:
        rows = [dict(row) for row in conn.execute("SELECT * FROM users ORDER BY id DESC")]
    for user in rows:
        try:
            user["remaining_days"] = max(
                0, (dt.date.fromisoformat(user["expire_date"]) - today).days
            )
        except Exception:
            user["remaining_days"] = 0
        user["xray_used_gb"] = (
            int(user["xray_rx_bytes"] or 0) + int(user["xray_tx_bytes"] or 0)
        ) / (1024 ** 3)
    return rows

@users_bp.get("/")
@login_required
def index():
    return render_template("index.html", users=list_users())

@users_bp.post("/users")
@login_required
def add_user():
    validate_csrf()
    try:
        username = request.form["username"].strip()
        password = request.form["password"]
        limit_gb = float(request.form["limit_gb"])
        days = int(request.form["days"])
        ssh_enabled = int("ssh" in request.form.getlist("protocols"))
        xray_enabled = int("xray" in request.form.getlist("protocols"))
        if not ssh_enabled and not xray_enabled:
            raise ValueError("حداقل یک پروتکل را انتخاب کن.")
        if get_user(username):
            raise ValueError("این نام کاربری قبلاً وجود دارد.")

        xray_uuid = str(uuid.uuid4()) if xray_enabled else None
        xray_email = f"{username}@panel.local" if xray_enabled else None
        expire = (dt.date.today() + dt.timedelta(days=days)).isoformat()

        if ssh_enabled:
            create_or_update(username, password)

        with connect() as conn:
            conn.execute("""
            INSERT INTO users(
              username,password,limit_gb,expire_date,ssh_enabled,xray_enabled,
              xray_uuid,xray_email
            ) VALUES(?,?,?,?,?,?,?,?)
            """, (
                username, password, limit_gb, expire, ssh_enabled, xray_enabled,
                xray_uuid, xray_email,
            ))
            conn.commit()

        if xray_enabled:
            regenerate()

        flash("کاربر ساخته شد.", "success")
    except Exception as exc:
        flash(f"خطا: {exc}", "error")
    return redirect(url_for("users.index"))

@users_bp.post("/users/<username>/edit")
@login_required
def edit_user(username):
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

        if user["ssh_enabled"]:
            create_or_update(username, password)

        with connect() as conn:
            conn.execute("""
            UPDATE users
            SET password=?,limit_gb=?,expire_date=?,updated_at=CURRENT_TIMESTAMP
            WHERE username=?
            """, (password, limit_gb, expire, username))
            conn.commit()

        flash("ویرایش ذخیره شد.", "success")
    except Exception as exc:
        flash(f"خطا: {exc}", "error")
    return redirect(url_for("users.index"))

@users_bp.post("/users/<username>/<action>")
@login_required
def user_action(username, action):
    validate_csrf()
    user = get_user(username)
    if not user:
        return redirect(url_for("users.index"))

    try:
        if action == "pause":
            if user["ssh_enabled"]:
                pause_linux(username)
            with connect() as conn:
                conn.execute("""
                UPDATE users SET paused=1,status='Paused',updated_at=CURRENT_TIMESTAMP
                WHERE username=?
                """, (username,))
                conn.commit()
            if user["xray_enabled"]:
                regenerate()

        elif action == "resume":
            if user["ssh_enabled"]:
                resume_linux(username)
            with connect() as conn:
                conn.execute("""
                UPDATE users SET paused=0,status='Active',updated_at=CURRENT_TIMESTAMP
                WHERE username=?
                """, (username,))
                conn.commit()
            if user["xray_enabled"]:
                regenerate()

        elif action == "reset-traffic":
            with connect() as conn:
                conn.execute("""
                UPDATE users SET xray_rx_bytes=0,xray_tx_bytes=0,updated_at=CURRENT_TIMESTAMP
                WHERE username=?
                """, (username,))
                conn.commit()

        elif action == "delete":
            if user["ssh_enabled"]:
                delete_linux(username)
            with connect() as conn:
                conn.execute("DELETE FROM users WHERE username=?", (username,))
                conn.commit()
            if user["xray_enabled"]:
                regenerate()

        flash("عملیات انجام شد.", "success")
    except Exception as exc:
        flash(f"خطا: {exc}", "error")
    return redirect(url_for("users.index"))

@users_bp.get("/users/<username>/xray")
@login_required
def xray_config(username):
    user = get_user(username)
    if not user or not user["xray_enabled"]:
        return ("Not found", 404)
    content = vmess_uri(user) + "\n"
    return send_file(
        BytesIO(content.encode()),
        as_attachment=True,
        download_name=f"{username}-vmess.txt",
        mimetype="text/plain",
    )

@users_bp.get("/users/<username>/ssh")
@login_required
def ssh_config(username):
    user = get_user(username)
    if not user or not user["ssh_enabled"]:
        return ("Not found", 404)
    content = (
        f"Server: {request.host.split(':')[0]}\n"
        f"Port: 22\n"
        f"Username: {user['username']}\n"
        f"Password: {user['password']}\n"
    )
    return send_file(
        BytesIO(content.encode()),
        as_attachment=True,
        download_name=f"{username}-ssh.txt",
        mimetype="text/plain",
    )
