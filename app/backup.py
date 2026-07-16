import json
from datetime import datetime, timezone
from io import BytesIO
from flask import Blueprint, flash, redirect, request, send_file, url_for

from .auth import login_required
from .db import connect
from .security import validate_csrf
from .system_accounts import create_or_update
from .xray_manager import regenerate

backup_bp = Blueprint("backup", __name__, url_prefix="/backup")

@backup_bp.get("/download")
@login_required
def download():
    with connect() as conn:
        users = [dict(row) for row in conn.execute("SELECT * FROM users ORDER BY id")]
    payload = {
        "format": "custom-panel-xray-ssh",
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "users": users,
    }
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode()
    return send_file(
        BytesIO(data),
        as_attachment=True,
        download_name="custom-panel-backup.json",
        mimetype="application/json",
    )

@backup_bp.post("/restore")
@login_required
def restore():
    validate_csrf()
    try:
        uploaded = request.files.get("backup_file")
        if not uploaded:
            raise ValueError("فایل انتخاب نشده است.")
        payload = json.load(uploaded.stream)
        users = payload.get("users", payload if isinstance(payload, list) else [])
        if not isinstance(users, list):
            raise ValueError("فرمت بکاپ معتبر نیست.")

        with connect() as conn:
            for user in users:
                if int(user.get("ssh_enabled", 1)):
                    create_or_update(user["username"], user["password"])
                conn.execute("""
                INSERT INTO users(
                  username,password,limit_gb,expire_date,paused,status,
                  ssh_enabled,xray_enabled,xray_uuid,xray_email,
                  xray_rx_bytes,xray_tx_bytes
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(username) DO UPDATE SET
                  password=excluded.password,
                  limit_gb=excluded.limit_gb,
                  expire_date=excluded.expire_date,
                  paused=excluded.paused,
                  status=excluded.status,
                  ssh_enabled=excluded.ssh_enabled,
                  xray_enabled=excluded.xray_enabled,
                  xray_uuid=excluded.xray_uuid,
                  xray_email=excluded.xray_email,
                  xray_rx_bytes=excluded.xray_rx_bytes,
                  xray_tx_bytes=excluded.xray_tx_bytes
                """, (
                    user["username"], user["password"], float(user.get("limit_gb", 0)),
                    user.get("expire_date"), int(bool(user.get("paused", 0))),
                    user.get("status", "Active"), int(bool(user.get("ssh_enabled", 1))),
                    int(bool(user.get("xray_enabled", 0))), user.get("xray_uuid"),
                    user.get("xray_email"), int(user.get("xray_rx_bytes", 0)),
                    int(user.get("xray_tx_bytes", 0)),
                ))
            conn.commit()

        regenerate()
        flash("بکاپ بازیابی شد.", "success")
    except Exception as exc:
        flash(f"خطا: {exc}", "error")
    return redirect(url_for("users.index"))
