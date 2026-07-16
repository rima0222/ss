import json
import subprocess
from datetime import datetime, timezone
from io import BytesIO

from flask import Blueprint, flash, redirect, request, send_file, url_for

from .auth import login_required
from .db import connect
from .linux_users import create_or_update
from .security import validate_csrf

backup_bp = Blueprint("backup", __name__, url_prefix="/backup")

@backup_bp.get("/download")
@login_required
def download():
    with connect() as c:
        users = [dict(r) for r in c.execute("SELECT * FROM users ORDER BY id")]
    payload = {
        "format": "custom-panel-optimized-ssh",
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
            raise ValueError("فایل بکاپ انتخاب نشده است.")
        payload = json.load(uploaded.stream)
        users = payload.get("users", [])
        if not isinstance(users, list):
            raise ValueError("ساختار بکاپ معتبر نیست.")

        with connect() as c:
            for user in users:
                create_or_update(user["username"], user["password"])
                c.execute("""
                INSERT INTO users(
                  id,username,password,port,limit_bytes,remaining_days,
                  paused,status,rx_bytes,tx_bytes,online,last_seen
                ) VALUES(?,?,?,?,?,?,?,?,?,?,0,?)
                ON CONFLICT(username) DO UPDATE SET
                  password=excluded.password,
                  port=excluded.port,
                  limit_bytes=excluded.limit_bytes,
                  remaining_days=excluded.remaining_days,
                  paused=excluded.paused,
                  status=excluded.status,
                  rx_bytes=excluded.rx_bytes,
                  tx_bytes=excluded.tx_bytes,
                  online=0,
                  last_seen=excluded.last_seen
                """, (
                    user.get("id"), user["username"], user["password"],
                    user["port"], user.get("limit_bytes", 0),
                    user.get("remaining_days", 0), user.get("paused", 0),
                    user.get("status", "Active"), user.get("rx_bytes", 0),
                    user.get("tx_bytes", 0), user.get("last_seen", 0),
                ))
            c.commit()

        subprocess.run(["systemctl", "restart", "custom-panel-proxy"], check=False)
        flash("بکاپ بازیابی شد.", "success")
    except Exception as exc:
        flash(f"خطا: {exc}", "error")
    return redirect(url_for("users.index"))
