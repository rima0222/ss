import logging
import subprocess
import time

from .config import Config
from .db import connect, init_db
from .linux_users import pause as pause_linux

INTERVAL = 15
DAY_SECONDS = 86400
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("accounting")

def restart_proxy():
    subprocess.run(["systemctl", "restart", "custom-panel-proxy"], check=False)

def enforce_limits():
    changed = False
    with connect() as c:
        users = [dict(r) for r in c.execute("SELECT * FROM users")]
        for user in users:
            used = int(user["rx_bytes"] or 0) + int(user["tx_bytes"] or 0)
            over_quota = int(user["limit_bytes"] or 0) > 0 and used >= int(user["limit_bytes"])
            out_of_time = int(user["remaining_days"] or 0) <= 0
            if not user["paused"] and (over_quota or out_of_time):
                try:
                    pause_linux(user["username"])
                except Exception:
                    log.exception("Could not lock %s", user["username"])
                c.execute("""
                UPDATE users SET paused=1,status='Expired',online=0
                WHERE id=?
                """, (user["id"],))
                changed = True
        c.commit()
    if changed:
        restart_proxy()

def decrement_days():
    with connect() as c:
        c.execute("""
        UPDATE users
        SET remaining_days=CASE
              WHEN remaining_days>0 THEN remaining_days-1
              ELSE 0
            END,
            updated_at=CURRENT_TIMESTAMP
        """)
        c.commit()

def main():
    init_db(Config.DB_PATH)
    last_day_tick = int(time.time())
    while True:
        try:
            now = int(time.time())
            if now - last_day_tick >= DAY_SECONDS:
                decrement_days()
                last_day_tick = now
            enforce_limits()
        except Exception:
            log.exception("Accounting check failed")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
