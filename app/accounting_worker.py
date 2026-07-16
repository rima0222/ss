import logging
import subprocess
import time
from datetime import date

from .config import Config
from .db import connect, init_db
from .linux_users import pause as pause_linux

INTERVAL = 10
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("accounting")

def tick():
    with connect() as c:
        users = [dict(r) for r in c.execute("SELECT * FROM users")]
        for u in users:
            used_gb = (int(u["rx_bytes"] or 0) + int(u["tx_bytes"] or 0)) / (1024**3)
            expired = False
            try:
                expired = date.fromisoformat(u["expire_date"]) < date.today()
            except Exception:
                pass
            over = float(u["limit_gb"] or 0) > 0 and used_gb >= float(u["limit_gb"])
            if not u["paused"] and (expired or over):
                try:
                    pause_linux(u["username"])
                except Exception:
                    log.exception("pause failed for %s", u["username"])
                c.execute("""
                UPDATE users SET paused=1,status='Expired',updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """, (u["id"],))
        c.commit()

def main():
    init_db(Config.DB_PATH)
    while True:
        try:
            tick()
        except Exception:
            log.exception("accounting tick failed")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
