import secrets
from flask import abort,session,request

def csrf_token():
    if '_csrf' not in session: session['_csrf']=secrets.token_urlsafe(24)
    return session['_csrf']

def validate_csrf():
    if request.form.get('_csrf') != session.get('_csrf'): abort(400,'Invalid CSRF token')
