import os
from flask import Blueprint, jsonify
from .auth import login_required
from .db import connect

api_bp = Blueprint("api", __name__, url_prefix="/api")

def memory_percent():
    values = {}
    for line in open("/proc/meminfo"):
        key, value = line.split(":", 1)
        values[key] = int(value.split()[0])
    return round((1 - values["MemAvailable"] / values["MemTotal"]) * 100, 1)

@api_bp.get("/stats")
@login_required
def stats():
    with connect() as conn:
        rows = [dict(row) for row in conn.execute("SELECT * FROM users ORDER BY id DESC")]
    online = sum(1 for row in rows if row["ssh_online"] or row["xray_online"])
    return jsonify({
        "total_users": len(rows),
        "active_users": sum(1 for row in rows if not row["paused"]),
        "online_users": online,
        "total_limit_gb": round(sum(float(row["limit_gb"] or 0) for row in rows), 3),
        "total_used_gb": round(sum(
            (int(row["xray_rx_bytes"] or 0) + int(row["xray_tx_bytes"] or 0)) / (1024 ** 3)
            for row in rows
        ), 3),
        "memory_percent": memory_percent(),
        "load": round(os.getloadavg()[0], 2),
        "users": {
            row["username"]: {
                "used_gb": round(
                    (int(row["xray_rx_bytes"] or 0) + int(row["xray_tx_bytes"] or 0)) / (1024 ** 3),
                    6,
                ),
                "ssh_online": bool(row["ssh_online"]),
                "xray_online": bool(row["xray_online"]),
            }
            for row in rows
        },
    })
