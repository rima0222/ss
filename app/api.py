import os
from flask import Blueprint, jsonify
from .auth import login_required
from .db import connect
from .users import human_bytes

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
        users = [dict(row) for row in conn.execute("SELECT * FROM users ORDER BY id DESC")]
    total_used = sum(int(u["rx_bytes"] or 0) + int(u["tx_bytes"] or 0) for u in users)
    return jsonify({
        "total_users": len(users),
        "active_users": sum(1 for u in users if not u["paused"]),
        "online_users": sum(1 for u in users if int(u["online_tcp"] or 0) > 0 or int(u["online_ws"] or 0) > 0),
        "total_limit_gb": round(sum(int(u["limit_bytes"] or 0) for u in users)/1024**3, 2),
        "total_used": human_bytes(total_used),
        "memory_percent": memory_percent(),
        "load": round(os.getloadavg()[0], 2),
        "users": {
            u["username"]: {
                "used": human_bytes(int(u["rx_bytes"] or 0)+int(u["tx_bytes"] or 0)),
                "used_bytes": int(u["rx_bytes"] or 0)+int(u["tx_bytes"] or 0),
                "limit_bytes": int(u["limit_bytes"] or 0),
                "online_tcp": int(u["online_tcp"] or 0) > 0,
                "online_ws": int(u["online_ws"] or 0) > 0,
                "remaining_days": int(u["remaining_days"] or 0),
            }
            for u in users
        },
    })
