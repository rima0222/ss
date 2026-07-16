import json
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
        counters=[dict(r) for r in c.execute("SELECT * FROM proxy_counters")]
    payload={
      "format":"custom-panel-ssh-suite",
      "version":1,
      "created_at":datetime.now(timezone.utc).isoformat(),
      "users":users,
      "proxy_counters":counters,
    }
    data=json.dumps(payload,ensure_ascii=False,indent=2).encode()
    return send_file(BytesIO(data),as_attachment=True,download_name="custom-panel-backup.json",mimetype="application/json")

@backup_bp.post("/restore")
@login_required
def restore():
    validate_csrf()
    try:
        uploaded=request.files.get("backup_file")
        payload=json.load(uploaded.stream)
        users=payload.get("users",[])
        counters=payload.get("proxy_counters",[])
        with connect() as c:
            for u in users:
                create_or_update(u["username"],u["password"])
                columns=[
                  "username","password","limit_gb","expire_date","paused","status",
                  "openssh_enabled","dropbear_enabled","ws_enabled","tls_enabled",
                  "openssh_port","dropbear_port","ws_port","tls_port","ws_token",
                  "rx_bytes","tx_bytes","online_count","last_seen"
                ]
                values=[u.get(col) for col in columns]
                placeholders=",".join("?" for _ in columns)
                update=",".join(f"{col}=excluded.{col}" for col in columns[1:])
                c.execute(f"""
                INSERT INTO users({",".join(columns)})
                VALUES({placeholders})
                ON CONFLICT(username) DO UPDATE SET {update}
                """,values)
            c.commit()

            idmap={r["username"]:r["id"] for r in c.execute("SELECT id,username FROM users")}
            c.execute("DELETE FROM proxy_counters")
            for counter in counters:
                old_uid=counter.get("user_id")
                # Backup keeps original ids, which are usually restored unchanged.
                c.execute("""
                INSERT OR REPLACE INTO proxy_counters(user_id,transport,rx_bytes,tx_bytes,online,last_seen)
                VALUES(?,?,?,?,0,?)
                """,(
                    old_uid,counter["transport"],counter.get("rx_bytes",0),
                    counter.get("tx_bytes",0),counter.get("last_seen",0)
                ))
            c.commit()

        import subprocess
        subprocess.run(["systemctl","restart","custom-panel-proxy"],check=False)
        flash("بکاپ بازیابی شد.","success")
    except Exception as exc:
        flash(f"خطا: {exc}","error")
    return redirect(url_for("users.index"))
