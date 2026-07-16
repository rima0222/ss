import os

class Config:
    SECRET_KEY = os.getenv("CUSTOM_PANEL_SECRET_KEY", "change-me")
    ADMIN_USERNAME = os.getenv("CUSTOM_PANEL_ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("CUSTOM_PANEL_ADMIN_PASSWORD", "change-me")
    DB_PATH = os.getenv("CUSTOM_PANEL_DB", "/etc/custom-panel/data/panel.db")
    SERVER_HOST = os.getenv("CUSTOM_PANEL_SERVER_HOST", "SERVER_IP")
    INTERNAL_SSH_PORT = int(os.getenv("CUSTOM_PANEL_INTERNAL_SSH_PORT", "2222"))
    PORT_START = int(os.getenv("CUSTOM_PANEL_PORT_START", "20000"))
    PORT_END = int(os.getenv("CUSTOM_PANEL_PORT_END", "29999"))
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
