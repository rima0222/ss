import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    db_path: str = os.getenv("CP_DB_PATH", "/var/lib/custom-panel/panel.db")
    manager_socket: str = os.getenv("CP_MANAGER_SOCKET", "/run/custom-panel/manager.sock")
    helper_socket: str = os.getenv("CP_HELPER_SOCKET", "/run/custom-panel/helper.sock")
    secret_key: str = os.getenv("CP_SECRET_KEY", "change-me")
    data_key: str = os.getenv("CP_DATA_KEY", "")
    server_host: str = os.getenv("CP_SERVER_HOST", "127.0.0.1")
    panel_port: int = int(os.getenv("CP_PANEL_PORT", "5000"))
    ws_port: int = int(os.getenv("CP_WS_PORT", "8080"))
    tcp_port_start: int = int(os.getenv("CP_TCP_PORT_START", "20000"))
    tcp_port_end: int = int(os.getenv("CP_TCP_PORT_END", "24999"))
    backend_port_start: int = int(os.getenv("CP_BACKEND_PORT_START", "30000"))
    backend_port_end: int = int(os.getenv("CP_BACKEND_PORT_END", "34999"))

settings = Settings()
