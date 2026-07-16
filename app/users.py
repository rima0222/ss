import datetime as dt,json
from flask import Blueprint,flash,redirect,render_template,request,url_for,send_file,current_app
from io import BytesIO
import qrcode
from .auth import login_required
from .db import connect
from .protocols import REGISTRY
from .security import validate_csrf
users_bp=Blueprint('users',__name__)

def list_users():
    today=dt.date.today()
    with connect() as c:
        rows=c.execute("""SELECT u.*,GROUP_CONCAT(CASE WHEN p.enabled=1 THEN p.protocol END) protocols
          FROM users u LEFT JOIN user_protocols p ON p.user_id=u.id GROUP BY u.id ORDER BY u.id DESC""").fetchall()
    users=[]
    for row in rows:
        item=dict(row)
        try:
            remaining=(dt.date.fromisoformat(item.get('expire_date'))-today).days
            item['remaining_days']=max(0,remaining)
        except (TypeError,ValueError):
            item['remaining_days']=0
        users.append(item)
    return users

def get_user(name):
    with connect() as c:
        x=c.execute('SELECT * FROM users WHERE username=?',(name,)).fetchone()
    return dict(x) if x else None

def enabled_protocols(uid):
    with connect() as c:return [x['protocol'] for x in c.execute('SELECT protocol FROM user_protocols WHERE user_id=? AND enabled=1',(uid,))]

@users_bp.get('/')
@login_required
def index(): return render_template('index.html',users=list_users())

@users_bp.post('/users')
@login_required
def add():
    validate_csrf(); created=[]
    try:
        name=request.form['username'].strip(); pw=request.form['password']; limit=float(request.form['limit_gb']); days=int(request.form['days'])
        if get_user(name): raise ValueError('این نام کاربری قبلاً در پنل ثبت شده است.')
        prots=list(dict.fromkeys(p for p in request.form.getlist('protocols') if p in REGISTRY)) or ['ssh']
        exp=(dt.date.today()+dt.timedelta(days=days)).isoformat()
        u={'username':name,'password':pw,'limit_gb':limit,'used_gb':0,'expire_date':exp,'status':'Active','paused':0,'initial_gb':limit,'initial_days':days}
        for p in prots: REGISTRY[p].create(u); created.append(p)
        with connect() as c:
            cur=c.execute('INSERT INTO users(username,password,limit_gb,expire_date,initial_gb,initial_days) VALUES(?,?,?,?,?,?)',(name,pw,limit,exp,limit,days)); uid=cur.lastrowid
            c.executemany('INSERT INTO user_protocols(user_id,protocol,enabled) VALUES(?,?,1)',[(uid,p) for p in prots]); c.commit()
        flash('کاربر با موفقیت ساخته شد.','success')
    except Exception as e:
        for p in reversed(created):
            try:REGISTRY[p].delete({'username':request.form.get('username','')})
            except Exception:pass
        flash(f'خطا: {e}','error')
    return redirect(url_for('users.index'))

@users_bp.post('/users/<name>/edit')
@login_required
def edit(name):
    validate_csrf(); u=get_user(name)
    if not u: return redirect(url_for('users.index'))
    try:
        pw=request.form.get('password') or u['password']; limit=float(request.form.get('limit_gb',u['limit_gb'])); used=float(request.form.get('used_gb',u['used_gb']))
        rem=request.form.get('remaining_days'); exp=(dt.date.today()+dt.timedelta(days=int(rem))).isoformat() if rem not in (None,'') else u['expire_date']
        nu={**u,'password':pw,'limit_gb':limit,'used_gb':used,'expire_date':exp}
        for p in enabled_protocols(u['id']): REGISTRY[p].update(nu)
        with connect() as c:c.execute('UPDATE users SET password=?,limit_gb=?,used_gb=?,expire_date=?,updated_at=CURRENT_TIMESTAMP WHERE username=?',(pw,limit,used,exp,name)); c.commit()
        flash('ویرایش ذخیره شد.','success')
    except Exception as e: flash(f'خطا: {e}','error')
    return redirect(url_for('users.index'))

@users_bp.post('/users/<name>/<action>')
@login_required
def state(name,action):
    validate_csrf(); u=get_user(name)
    try:
        if not u: raise ValueError('کاربر پیدا نشد')
        if action in ('pause','resume'):
            for p in enabled_protocols(u['id']): getattr(REGISTRY[p],action)(u)
            paused=1 if action=='pause' else 0; status='Paused' if paused else 'Active'
            with connect() as c:c.execute('UPDATE users SET paused=?,status=? WHERE username=?',(paused,status,name)); c.commit()
        elif action=='delete':
            for p in enabled_protocols(u['id']): REGISTRY[p].delete(u)
            with connect() as c:c.execute('DELETE FROM users WHERE username=?',(name,)); c.commit()
        flash('عملیات انجام شد.','success')
    except Exception as e: flash(f'خطا: {e}','error')
    return redirect(url_for('users.index'))

@users_bp.get('/users/<name>/config/<protocol>')
@login_required
def config(name,protocol):
    u=get_user(name)
    if not u or protocol not in REGISTRY: return ('Not found',404)
    x=REGISTRY[protocol].client(u); data=x['content'].encode()
    return send_file(BytesIO(data),as_attachment=True,download_name=x['filename'],mimetype='text/plain')

@users_bp.get('/users/<name>/qr')
@login_required
def qr(name):
    u=get_user(name); x=REGISTRY['wireguard'].client(u); img=qrcode.make(x['content']); out=BytesIO(); img.save(out,'PNG'); out.seek(0)
    return send_file(out,mimetype='image/png',download_name=f'{name}-wireguard.png')
