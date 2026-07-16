import os

class Config:
    SECRET_KEY = os.environ["CUSTOM_PANEL_SECRET_KEY"]
    ADMIN_USERNAME = os.getenv("CUSTOM_PANEL_ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD_HASH = os.environ["CUSTOM_PANEL_ADMIN_PASSWORD_HASH"]
    DATA_KEY = os.environ["CUSTOM_PANEL_DATA_KEY"]
    DB_PATH = os.getenv("CUSTOM_PANEL_DB", "/etc/custom-panel/data/panel.db")
    SERVER_HOST = os.getenv("CUSTOM_PANEL_SERVER_HOST", "SERVER_IP")
    INTERNAL_SSH_PORT = int(os.getenv("CUSTOM_PANEL_INTERNAL_SSH_PORT", "2222"))
    PORT_START = int(os.getenv("CUSTOM_PANEL_PORT_START", "20000"))
    PORT_END = int(os.getenv("CUSTOM_PANEL_PORT_END", "29999"))
    HELPER_SOCKET = os.getenv("CUSTOM_PANEL_HELPER_SOCKET", "/run/custom-panel/helper.sock")
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Strict"
    SESSION_COOKIE_SECURE = os.getenv("CUSTOM_PANEL_COOKIE_SECURE", "0") == "1"
