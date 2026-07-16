from functools import wraps
from flask import Blueprint,current_app,render_template,request,session,redirect,url_for
from werkzeug.security import check_password_hash,generate_password_hash
from .security import csrf_token,validate_csrf

auth_bp=Blueprint('auth',__name__)

def login_required(fn):
    @wraps(fn)
    def inner(*a,**kw):
        return fn(*a,**kw) if session.get('admin') else redirect(url_for('auth.login'))
    return inner

@auth_bp.app_context_processor
def inject(): return {'csrf_token':csrf_token}

@auth_bp.route('/login',methods=['GET','POST'])
def login():
    error=None
    if request.method=='POST':
        validate_csrf(); u=request.form.get('username',''); p=request.form.get('password','')
        stored=current_app.config['ADMIN_PASSWORD']
        ok=check_password_hash(stored,p) if stored.startswith(('scrypt:','pbkdf2:')) else secrets_compare(stored,p)
        if u==current_app.config['ADMIN_USERNAME'] and ok:
            session.clear(); session['admin']=True; return redirect(url_for('users.index'))
        error='نام کاربری یا رمز عبور اشتباه است.'
    return render_template('login.html',error=error)

def secrets_compare(a,b):
    import hmac
    return hmac.compare_digest(str(a),str(b))

@auth_bp.get('/logout')
def logout(): session.clear(); return redirect(url_for('auth.login'))
