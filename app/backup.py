import json
import subprocess
from datetime import datetime, timezone
from io import BytesIO
from flask import Blueprint, flash, redirect, request, send_file, url_for

from .auth import login_required
from .db import connect
from .linux_users import create_or_update
from .security import validate_csrf

backup_bp=Blueprint("backup",__name__,url_prefix="/backup")

@backup_bp.get("/download")
@login_required
def download():
    with connect() as c:
        users=[dict(r) for r in c.execute("SELECT * FROM users ORDER BY id")]
        usage=[dict(r) for r in c.execute("SELECT * FROM transport_usage")]
    payload={"format":"custom-panel-ssh-suite","version":2,
             "created_at":datetime.now(timezone.utc).isoformat(),
             "users":users,"transport_usage":usage}
    data=json.dumps(payload,ensure_ascii=False,indent=2).encode()
    return send_file(BytesIO(data),as_attachment=True,download_name="custom-panel-backup.json",mimetype="application/json")

@backup_bp.post("/restore")
@login_required
def restore():
    validate_csrf()
    try:
        uploaded=request.files.get("backup_file")
        if not uploaded:
            raise ValueError("فایل بکاپ انتخاب نشده است.")
        payload=json.load(uploaded.stream)
        users=payload.get("users",[])
        usage=payload.get("transport_usage",[])
        with connect() as c:
            c.execute("DELETE FROM transport_usage")
            for u in users:
                create_or_update(u["username"],u["password"])
                columns=[
                  "id","username","password","limit_gb","expire_date","paused","status",
                  "openssh_enabled","dropbear_enabled","ws_enabled","tls_enabled",
                  "openssh_port","dropbear_port","ws_port","tls_port","ws_token",
                  "rx_bytes","tx_bytes","online_count","last_seen"
                ]
                values=[u.get(col) for col in columns]
                placeholders=",".join("?" for _ in columns)
                update=",".join(f"{col}=excluded.{col}" for col in columns[2:])
                c.execute(f"""
                INSERT INTO users({",".join(columns)}) VALUES({placeholders})
                ON CONFLICT(username) DO UPDATE SET {update}
                """,values)
            for item in usage:
                c.execute("""
                INSERT OR REPLACE INTO transport_usage(user_id,transport,rx_bytes,tx_bytes,online,last_seen)
                VALUES(?,?,?,?,0,?)
                """,(item["user_id"],item["transport"],item.get("rx_bytes",0),item.get("tx_bytes",0),item.get("last_seen",0)))
            c.commit()
        subprocess.run(["systemctl","restart","custom-panel-proxy"],check=False)
        flash("بکاپ بازیابی شد.","success")
    except Exception as exc:
        flash(f"خطا: {exc}","error")
    return redirect(url_for("users.index"))
