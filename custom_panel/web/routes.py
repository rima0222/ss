import json
from io import BytesIO

from flask import Blueprint, flash, redirect, render_template, request, send_file, session, url_for

from ..ipc import request as manager_request
from ..settings import settings
from .common import csrf_token, login_required, verify_csrf

panel_bp = Blueprint("panel", __name__)

def call(method, params=None):
    return manager_request(
        settings.manager_socket,
        {"method": method, "params": params or {}},
        timeout=45,
    )

@panel_bp.get("/")
@login_required
def dashboard():
    return render_template("dashboard.html", csrf_token=csrf_token)

@panel_bp.post("/users/create")
@login_required
def create_user():
    verify_csrf()
    try:
        call("user.create", {
            "username": request.form.get("username", ""),
            "password": request.form.get("password", ""),
            "quota_gb": request.form.get("quota_gb", "0"),
            "days": request.form.get("days", "30"),
            "tcp_enabled": "tcp_enabled" in request.form,
            "ws_enabled": "ws_enabled" in request.form,
        })
        flash("کاربر ساخته شد.", "success")
    except Exception as exc:
        flash(f"خطا: {exc}", "error")
    return redirect(url_for("panel.dashboard"))

@panel_bp.post("/users/<username>/edit")
@login_required
def edit_user(username):
    verify_csrf()
    try:
        call("user.edit", {
            "username": username,
            "password": request.form.get("password", ""),
            "quota_gb": request.form.get("quota_gb", "0"),
            "days": request.form.get("days", "30"),
            "tcp_enabled": "tcp_enabled" in request.form,
            "ws_enabled": "ws_enabled" in request.form,
        })
        flash("تغییرات ذخیره شد.", "success")
    except Exception as exc:
        flash(f"خطا: {exc}", "error")
    return redirect(url_for("panel.dashboard"))

@panel_bp.post("/users/<username>/<action>")
@login_required
def user_action(username, action):
    verify_csrf()
    methods = {
        "pause": "user.pause",
        "resume": "user.resume",
        "delete": "user.delete",
        "reset-usage": "user.reset_usage",
    }
    try:
        if action not in methods:
            raise ValueError("عملیات نامعتبر است.")
        call(methods[action], {"username": username})
        flash("عملیات انجام شد.", "success")
    except Exception as exc:
        flash(f"خطا: {exc}", "error")
    return redirect(url_for("panel.dashboard"))

@panel_bp.get("/users/<username>/config")
@login_required
def user_config(username):
    data = call("user.config", {"username": username})
    lines = [
        f"Server: {data['server']}",
        f"Username: {data['username']}",
        f"Password: {data['password']}",
        "",
    ]
    if data["tcp_enabled"]:
        lines += ["OpenSSH TCP", f"Host: {data['server']}", f"Port: {data['tcp_port']}", ""]
    if data["ws_enabled"]:
        lines += [
            "SSH WebSocket",
            f"URL: {data['ws_url']}",
            f"Host: {data['server']}",
            f"Port: {data['ws_port']}",
            f"Path: {data['ws_path']}",
            "",
        ]
    return send_file(
        BytesIO("\n".join(lines).encode()),
        as_attachment=True,
        download_name=f"{username}-ssh.txt",
        mimetype="text/plain",
    )

@panel_bp.post("/admin/change")
@login_required
def change_admin():
    verify_csrf()
    try:
        call("admin.change", {
            "username": request.form.get("admin_username", ""),
            "password": request.form.get("admin_password", ""),
        })
        session.clear()
        flash("اطلاعات مدیر تغییر کرد. دوباره وارد شو.", "success")
        return redirect(url_for("auth.login"))
    except Exception as exc:
        flash(f"خطا: {exc}", "error")
        return redirect(url_for("panel.dashboard"))

@panel_bp.get("/backup")
@login_required
def backup():
    payload = call("backup.export")
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode()
    return send_file(
        BytesIO(data),
        as_attachment=True,
        download_name="custom-panel-backup.json",
        mimetype="application/json",
    )

@panel_bp.post("/restore")
@login_required
def restore():
    verify_csrf()
    try:
        uploaded = request.files.get("backup_file")
        if not uploaded:
            raise ValueError("فایل بکاپ انتخاب نشده است.")
        payload = json.load(uploaded.stream)
        call("backup.restore", {"backup": payload})
        flash("بکاپ بازیابی شد.", "success")
    except Exception as exc:
        flash(f"خطا: {exc}", "error")
    return redirect(url_for("panel.dashboard"))
