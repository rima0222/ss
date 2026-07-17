import hmac
import secrets
from functools import wraps

from flask import abort, redirect, request, session, url_for

def csrf_token():
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token

def verify_csrf():
    supplied = request.form.get("_csrf", "") or request.headers.get("X-CSRF-Token", "")
    expected = session.get("_csrf", "")
    if not supplied or not expected or not hmac.compare_digest(supplied, expected):
        abort(400, "Invalid CSRF token")

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped
