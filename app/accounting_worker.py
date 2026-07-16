import datetime as dt
import logging
import subprocess
import time

from .config import Config
from .db import connect, init_db

INTERVAL = 10
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("accounting")

def helper(action, username):
    import json, socket
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(15)
        sock.connect(Config.HELPER_SOCKET)
        sock.sendall((json.dumps({"action": action, "username": username}) + "\n").encode())
        response = b""
        while not response.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                break
            response += chunk
    result = json.loads(response.decode())
    if not result.get("ok"):
        raise RuntimeError(result.get("error", "helper failed"))

def apply_day_rollover():
    today = dt.date.today()
    with connect() as conn:
        row = conn.execute("SELECT value FROM metadata WHERE key='last_rollover'").fetchone()
        if row:
            last = dt.date.fromisoformat(row["value"])
        else:
            last = today
            conn.execute(
                "INSERT OR REPLACE INTO metadata(key,value) VALUES('last_rollover',?)",
                (today.isoformat(),),
            )
            conn.commit()
            return

        elapsed = (today - last).days
        if elapsed <= 0:
            return

        conn.execute("""
        UPDATE users
        SET remaining_days=MAX(0,remaining_days-?),
            updated_at=CURRENT_TIMESTAMP
        """, (elapsed,))
        conn.execute(
            "INSERT OR REPLACE INTO metadata(key,value) VALUES('last_rollover',?)",
            (today.isoformat(),),
        )
        conn.commit()

def enforce():
    changed = False
    with connect() as conn:
        users = [dict(row) for row in conn.execute("SELECT * FROM users")]
        for user in users:
            used = int(user["rx_bytes"] or 0) + int(user["tx_bytes"] or 0)
            over = int(user["limit_bytes"] or 0) > 0 and used >= int(user["limit_bytes"])
            expired = int(user["remaining_days"] or 0) <= 0
            if not user["paused"] and (over or expired):
                try:
                    helper("pause", user["username"])
                except Exception:
                    log.exception("Could not pause %s", user["username"])
                conn.execute("""
                UPDATE users SET paused=1,status='Expired',online=0
                WHERE id=?
                """, (user["id"],))
                changed = True
        conn.commit()

def main():
    init_db(Config.DB_PATH)
    while True:
        try:
            apply_day_rollover()
            enforce()
        except Exception:
            log.exception("Accounting cycle failed")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
