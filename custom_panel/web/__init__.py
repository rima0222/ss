from flask import Flask
from ..db import initialize
from ..settings import settings
from .auth import auth_bp
from .routes import panel_bp
from .api import api_bp
from .common import csrf_token

def create_app():
    initialize(settings.db_path)
    app = Flask(
        __name__,
        template_folder="../../templates",
        static_folder="../../static",
    )
    app.secret_key = settings.secret_key
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
    )
    app.register_blueprint(auth_bp)
    app.register_blueprint(panel_bp)
    app.register_blueprint(api_bp)
    return app
