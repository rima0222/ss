import datetime as dt,json
from io import BytesIO
from flask import Blueprint,flash,redirect,request,send_file,url_for
from .auth import login_required
from .db import connect
from .protocols import REGISTRY
from .security import validate_csrf
backup_bp=Blueprint('backup',__name__,url_prefix='/backup')

def export_data():
    with connect() as c:
        users=[]
        for r in c.execute('SELECT * FROM users ORDER BY id'):
            x=dict(r); x['protocols']=[dict(p) for p in c.execute('SELECT protocol,enabled,config_json FROM user_protocols WHERE user_id=?',(r['id'],))]; users.append(x)
    return {'format':'custom-panel-backup','version':2,'created_at':dt.datetime.now(dt.timezone.utc).isoformat(),'users':users}

def normalize(d):
    if isinstance(d,list):
        return {'version':1,'users':[{**x,'paused':0,'protocols':[{'protocol':'ssh','enabled':1,'config_json':'{}'}]} for x in d]}
    if isinstance(d,dict) and isinstance(d.get('users'),list): return d
    raise ValueError('فرمت بکاپ نامعتبر است')

@backup_bp.get('/download')
@login_required
def download():
    b=json.dumps(export_data(),ensure_ascii=False,indent=2).encode(); return send_file(BytesIO(b),as_attachment=True,download_name='custom-panel-backup.json',mimetype='application/json')

@backup_bp.post('/restore')
@login_required
def restore():
    validate_csrf()
    try:
        f=request.files.get('backup_file'); d=normalize(json.load(f.stream))
        for x in d['users']:
            u={'username':x['username'],'password':x['password'],'limit_gb':float(x.get('limit_gb') or 0),'used_gb':float(x.get('used_gb') or 0),'expire_date':x.get('expire_date'),'status':x.get('status','Active'),'paused':int(bool(x.get('paused',0))),'initial_gb':float(x.get('initial_gb') or x.get('limit_gb') or 0),'initial_days':int(x.get('initial_days') or 0)}
            prots=x.get('protocols') or [{'protocol':'ssh','enabled':1,'config_json':'{}'}]
            for p in prots:
                if p.get('enabled',1) and p.get('protocol') in REGISTRY:
                    try: REGISTRY[p['protocol']].create(u)
                    except Exception: pass
            with connect() as c:
                c.execute("""INSERT INTO users(username,password,limit_gb,used_gb,expire_date,status,paused,initial_gb,initial_days)
                VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(username) DO UPDATE SET password=excluded.password,limit_gb=excluded.limit_gb,used_gb=excluded.used_gb,expire_date=excluded.expire_date,status=excluded.status,paused=excluded.paused,initial_gb=excluded.initial_gb,initial_days=excluded.initial_days""",tuple(u[k] for k in ('username','password','limit_gb','used_gb','expire_date','status','paused','initial_gb','initial_days')))
                uid=c.execute('SELECT id FROM users WHERE username=?',(u['username'],)).fetchone()['id']; c.execute('DELETE FROM user_protocols WHERE user_id=?',(uid,))
                c.executemany('INSERT INTO user_protocols(user_id,protocol,enabled,config_json) VALUES(?,?,?,?)',[(uid,p['protocol'],int(p.get('enabled',1)),p.get('config_json','{}')) for p in prots if p.get('protocol') in REGISTRY]); c.commit()
            if u['paused']:
                for p in prots:
                    if p.get('enabled',1) and p.get('protocol') in REGISTRY:
                        try: REGISTRY[p['protocol']].pause(u)
                        except Exception: pass
        flash('بکاپ با موفقیت بازیابی شد.','success')
    except Exception as e: flash(f'خطای بازیابی: {e}','error')
    return redirect(url_for('users.index'))
