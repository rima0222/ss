import os
from flask import Blueprint, jsonify, current_app
from .auth import login_required
from .db import connect
from .live import collect_live

api_bp = Blueprint('api', __name__, url_prefix='/api')


def mem():
    d = {}
    with open('/proc/meminfo') as f:
        for line in f:
            key, value = line.split(':', 1)
            d[key] = int(value.strip().split()[0])
    return round((d['MemTotal'] - d.get('MemAvailable', d['MemFree'])) / d['MemTotal'] * 100, 1)


def cpu():
    load = os.getloadavg()
    return {'one': round(load[0], 2), 'five': round(load[1], 2), 'fifteen': round(load[2], 2)}


def user_rows():
    with connect() as c:
        rows = c.execute("""
            SELECT u.*, GROUP_CONCAT(CASE WHEN p.enabled=1 THEN p.protocol END) AS protocols
            FROM users u
            LEFT JOIN user_protocols p ON p.user_id=u.id
            GROUP BY u.id
            ORDER BY u.id DESC
        """).fetchall()
    return [dict(row) for row in rows]


@api_bp.get('/stats')
@login_required
def stats():
    users = user_rows()
    live = collect_live(users, current_app.config['WG_INTERFACE'])
    with connect() as c:
        summary = c.execute("""
            SELECT COUNT(*) users,
                   SUM(CASE WHEN paused=0 THEN 1 ELSE 0 END) active,
                   COALESCE(SUM(limit_gb),0) quota,
                   COALESCE(SUM(used_gb),0) used
            FROM users
        """).fetchone()
    online = sum(1 for item in live.values() if item['online'])
    return jsonify({
        **dict(summary),
        'online': online,
        'memory_percent': mem(),
        'load': cpu(),
        'uptime_seconds': int(float(open('/proc/uptime').read().split()[0])),
        'user_usage': {
            item['username']: round(float(item.get('used_gb') or 0), 6)
            for item in users
        },
    })


@api_bp.get('/live')
@login_required
def live():
    users = user_rows()
    return jsonify({'users': collect_live(users, current_app.config['WG_INTERFACE'])})
