import os,time
from flask import Blueprint,jsonify
from .auth import login_required
from .db import connect
api_bp=Blueprint('api',__name__,url_prefix='/api')

def mem():
    d={}
    with open('/proc/meminfo') as f:
        for l in f:
            k,v=l.split(':',1); d[k]=int(v.strip().split()[0])
    return round((d['MemTotal']-d.get('MemAvailable',d['MemFree']))/d['MemTotal']*100,1)

def cpu():
    l=os.getloadavg(); return {'one':round(l[0],2),'five':round(l[1],2),'fifteen':round(l[2],2)}

@api_bp.get('/stats')
@login_required
def stats():
    with connect() as c:
        s=c.execute("SELECT COUNT(*) users,SUM(CASE WHEN paused=0 THEN 1 ELSE 0 END) active,COALESCE(SUM(limit_gb),0) quota,COALESCE(SUM(used_gb),0) used FROM users").fetchone()
    return jsonify({**dict(s),'memory_percent':mem(),'load':cpu(),'uptime_seconds':int(float(open('/proc/uptime').read().split()[0]))})
