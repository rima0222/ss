import os

class Config:
    SECRET_KEY = os.getenv("CUSTOM_PANEL_SECRET_KEY", "change-me")
    ADMIN_USERNAME = os.getenv("CUSTOM_PANEL_ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("CUSTOM_PANEL_ADMIN_PASSWORD", "change-me")
    DB_PATH = os.getenv("CUSTOM_PANEL_DB", "/etc/custom-panel/data/panel.db")
    SERVER_HOST = os.getenv("CUSTOM_PANEL_SERVER_HOST", "SERVER_IP")
    TLS_CERT = os.getenv("CUSTOM_PANEL_TLS_CERT", "/etc/custom-panel/tls/server.crt")
    TLS_KEY = os.getenv("CUSTOM_PANEL_TLS_KEY", "/etc/custom-panel/tls/server.key")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
