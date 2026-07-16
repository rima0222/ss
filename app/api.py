import os
from flask import Blueprint, jsonify

from .auth import login_required
from .db import connect
from .users import list_users

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
    users = list_users()
    with connect() as c:
        summary = c.execute("""
        SELECT COUNT(*) total_users,
               SUM(CASE WHEN paused=0 AND status='Active' THEN 1 ELSE 0 END) active_users,
               COALESCE(SUM(limit_gb),0) total_limit_gb,
               COALESCE(SUM(used_gb),0) total_used_gb
        FROM users
        """).fetchone()
        online = c.execute("""
        SELECT COUNT(DISTINCT user_id) n FROM protocol_usage WHERE online=1
        """).fetchone()["n"]

    return jsonify({
        **dict(summary),
        "online": online,
        "memory_percent": memory_percent(),
        "load": round(os.getloadavg()[0], 2),
        "user_usage": {
            u["username"]: {
                "total_gb": round(float(u.get("used_gb") or 0), 6),
                "protocols": {
                    p: {
                        "gb": round((int(s.get("rx_bytes") or 0) + int(s.get("tx_bytes") or 0)) / (1024**3), 6),
                        "online": bool(s.get("online")),
                    }
                    for p, s in u.get("protocol_usage", {}).items()
                },
            }
            for u in users
        },
    })
