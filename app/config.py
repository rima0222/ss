import os

class Config:
    SECRET_KEY = os.getenv("CUSTOM_PANEL_SECRET_KEY", "change-me")
    ADMIN_USERNAME = os.getenv("CUSTOM_PANEL_ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("CUSTOM_PANEL_ADMIN_PASSWORD", "change-me")
    DB_PATH = os.getenv("CUSTOM_PANEL_DB", "/etc/custom-panel/data/panel.db")
    SERVER_HOST = os.getenv("CUSTOM_PANEL_SERVER_HOST", "SERVER_IP")
    WG_INTERFACE = os.getenv("CUSTOM_PANEL_WG_INTERFACE", "wg0")
    WG_PORT = int(os.getenv("CUSTOM_PANEL_WG_PORT", "51820"))
    OVPN_PORT = int(os.getenv("CUSTOM_PANEL_OVPN_PORT", "1194"))
    IKE_REMOTE_ID = os.getenv("CUSTOM_PANEL_IKE_REMOTE_ID", SERVER_HOST)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
