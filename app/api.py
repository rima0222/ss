import os
from flask import Blueprint, jsonify
from .auth import login_required
from .db import connect

api_bp = Blueprint("api", __name__, url_prefix="/api")

def memory_percent():
    vals={}
    for line in open("/proc/meminfo"):
        k,v=line.split(":",1)
        vals[k]=int(v.split()[0])
    return round((1-vals["MemAvailable"]/vals["MemTotal"])*100,1)

@api_bp.get("/stats")
@login_required
def stats():
    with connect() as c:
        users=[dict(r) for r in c.execute("SELECT * FROM users ORDER BY id DESC")]
    return jsonify({
        "total_users":len(users),
        "active_users":sum(1 for u in users if not u["paused"]),
        "online_users":sum(1 for u in users if int(u["online_count"] or 0)>0),
        "total_limit_gb":round(sum(float(u["limit_gb"] or 0) for u in users),3),
        "total_used_gb":round(sum((int(u["rx_bytes"] or 0)+int(u["tx_bytes"] or 0))/(1024**3) for u in users),3),
        "memory_percent":memory_percent(),
        "load":round(os.getloadavg()[0],2),
        "users":{
          u["username"]:{
            "used_gb":round((int(u["rx_bytes"] or 0)+int(u["tx_bytes"] or 0))/(1024**3),6),
            "online":int(u["online_count"] or 0)>0,
          } for u in users
        },
    })
