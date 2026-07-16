import datetime as dt
import json
from io import BytesIO

from flask import Blueprint, flash, redirect, request, send_file, url_for

from .auth import login_required
from .db import connect
from .protocols import REGISTRY
from .security import validate_csrf

backup_bp = Blueprint("backup", __name__, url_prefix="/backup")

def export_data():
    with connect() as c:
        users = []
        for row in c.execute("SELECT * FROM users ORDER BY id"):
            item = dict(row)
            item["protocols"] = [
                dict(p) for p in c.execute(
                    "SELECT protocol,enabled,identifier,config_json FROM user_protocols WHERE user_id=?",
                    (row["id"],),
                )
            ]
            item["usage"] = [
                dict(p) for p in c.execute(
                    "SELECT protocol,rx_bytes,tx_bytes FROM protocol_usage WHERE user_id=?",
                    (row["id"],),
                )
            ]
            users.append(item)
    return {
        "format": "custom-panel-backup",
        "version": 3,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "users": users,
    }

def normalize(data):
    if isinstance(data, list):
        return {
            "version": 1,
            "users": [
                {**x, "paused": 0, "protocols": [{"protocol": "ssh", "enabled": 1, "config_json": "{}"}]}
                for x in data
            ],
        }
    if isinstance(data, dict) and isinstance(data.get("users"), list):
        return data
    raise ValueError("فرمت بکاپ نامعتبر است.")

@backup_bp.get("/download")
@login_required
def download():
    payload = json.dumps(export_data(), ensure_ascii=False, indent=2).encode()
    return send_file(
        BytesIO(payload),
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
        data = normalize(json.load(uploaded.stream))
        for source in data["users"]:
            user = {
                "username": source["username"],
                "password": source["password"],
                "limit_gb": float(source.get("limit_gb") or 0),
                "used_gb": float(source.get("used_gb") or 0),
                "expire_date": source.get("expire_date"),
                "status": source.get("status", "Active"),
                "paused": int(bool(source.get("paused", 0))),
                "initial_gb": float(source.get("initial_gb") or source.get("limit_gb") or 0),
                "initial_days": int(source.get("initial_days") or 0),
            }
            protocols = source.get("protocols") or [{"protocol": "ssh", "enabled": 1, "config_json": "{}"}]
            generated = {}
            for item in protocols:
                protocol = item.get("protocol")
                if item.get("enabled", 1) and protocol in REGISTRY:
                    generated[protocol] = REGISTRY[protocol].create(user)

            with connect() as c:
                c.execute("""
                INSERT INTO users(username,password,limit_gb,used_gb,expire_date,status,paused,initial_gb,initial_days)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(username) DO UPDATE SET
                  password=excluded.password,limit_gb=excluded.limit_gb,
                  expire_date=excluded.expire_date,status=excluded.status,
                  paused=excluded.paused,initial_gb=excluded.initial_gb,
                  initial_days=excluded.initial_days
                """, tuple(user[k] for k in (
                    "username","password","limit_gb","used_gb","expire_date",
                    "status","paused","initial_gb","initial_days"
                )))
                uid = c.execute("SELECT id FROM users WHERE username=?", (user["username"],)).fetchone()["id"]
                c.execute("DELETE FROM user_protocols WHERE user_id=?", (uid,))
                for item in protocols:
                    protocol = item.get("protocol")
                    if protocol not in REGISTRY:
                        continue
                    meta = generated.get(protocol, {})
                    c.execute("""
                    INSERT INTO user_protocols(user_id,protocol,enabled,identifier,config_json)
                    VALUES(?,?,?,?,?)
                    """, (
                        uid, protocol, int(item.get("enabled", 1)),
                        meta.get("identifier") or item.get("identifier"),
                        json.dumps(meta.get("config") or json.loads(item.get("config_json") or "{}")),
                    ))
                    c.execute("INSERT OR IGNORE INTO protocol_usage(user_id,protocol) VALUES(?,?)", (uid, protocol))
                c.commit()

            if user["paused"]:
                for item in protocols:
                    protocol = item.get("protocol")
                    if item.get("enabled", 1) and protocol in REGISTRY:
                        REGISTRY[protocol].pause(user)

        flash("بکاپ بازیابی شد.", "success")
    except Exception as exc:
        flash(f"خطای بازیابی: {exc}", "error")
    return redirect(url_for("users.index"))
