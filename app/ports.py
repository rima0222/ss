from flask import current_app
from .db import connect

def allocate():
    start = current_app.config["PORT_START"]
    end = current_app.config["PORT_END"]
    with connect() as c:
        used = {int(row["port"]) for row in c.execute("SELECT port FROM users")}
    for port in range(start, end + 1):
        if port not in used:
            return port
    raise RuntimeError("ظرفیت پورت‌های کاربران تکمیل شده است.")
