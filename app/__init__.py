from flask import Flask
from .config import Config
from .db import init_db
from .auth import auth_bp
from .users import users_bp
from .backup import backup_bp
from .api import api_bp

def create_app():
    app=Flask(__name__,template_folder='../templates',static_folder='../static')
    app.config.from_object(Config)
    init_db(app.config['DB_PATH'])
    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(backup_bp)
    app.register_blueprint(api_bp)
    return app
