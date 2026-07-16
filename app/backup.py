import json
import subprocess
from datetime import datetime, timezone
from io import BytesIO

from flask import Blueprint, flash, redirect, request, send_file, url_for

from .auth import login_required
from .crypto import decrypt, encrypt
from .db import connect
from .helper_client import request_helper
from .security import validate_csrf

backup_bp = Blueprint("backup", __name__, url_prefix="/backup")

@backup_bp.get("/download")
@login_required
def download():
    with connect() as conn:
        rows = [dict(row) for row in conn.execute("SELECT * FROM users ORDER BY id")]
    users = []
    for row in rows:
        item = dict(row)
        item["password"] = decrypt(item.pop("password_enc"))
        users.append(item)

    payload = {
        "format": "custom-panel-v7",
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

        with connect() as conn:
            for user in users:
                request_helper("upsert", user["username"], user["password"])
                conn.execute("""
                INSERT INTO users(
                  id,username,password_enc,port,limit_bytes,remaining_days,
                  paused,status,rx_bytes,tx_bytes,online,last_seen
                ) VALUES(?,?,?,?,?,?,?,?,?,?,0,?)
                ON CONFLICT(username) DO UPDATE SET
                  password_enc=excluded.password_enc,
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
                    user.get("id"),
                    user["username"],
                    encrypt(user["password"]),
                    user["port"],
                    user.get("limit_bytes", 0),
                    user.get("remaining_days", 0),
                    user.get("paused", 0),
                    user.get("status", "Active"),
                    user.get("rx_bytes", 0),
                    user.get("tx_bytes", 0),
                    user.get("last_seen", 0),
                ))
            conn.commit()

        subprocess.run(["systemctl", "restart", "custom-panel-proxy"], check=False)
        flash("بکاپ بازیابی شد.", "success")
    except Exception as exc:
        flash(f"خطا: {exc}", "error")
    return redirect(url_for("users.index"))
