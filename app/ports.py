from flask import current_app
from .db import connect

def allocate():
    start = current_app.config["PORT_START"]
    end = current_app.config["PORT_END"]
    with connect() as conn:
        used = {int(row["port"]) for row in conn.execute("SELECT port FROM users")}
    for port in range(start, end + 1):
        if port not in used:
            return port
    raise RuntimeError("ظرفیت پورت‌ها تکمیل شده است.")
