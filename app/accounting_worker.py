import logging
import subprocess
import time
from datetime import date

from .config import Config
from .db import connect, init_db
from .linux_users import pause as pause_linux

INTERVAL=10
logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
log=logging.getLogger("accounting")

def restart_proxy():
    subprocess.run(["systemctl","restart","custom-panel-proxy"],check=False)

def tick():
    changed=False
    with connect() as c:
        users=[dict(r) for r in c.execute("SELECT * FROM users")]
        for u in users:
            used=(int(u["rx_bytes"] or 0)+int(u["tx_bytes"] or 0))/(1024**3)
            try:
                expired=date.fromisoformat(u["expire_date"]) < date.today()
            except Exception:
                expired=False
            over=float(u["limit_gb"] or 0)>0 and used>=float(u["limit_gb"])
            if not u["paused"] and (expired or over):
                try:
                    pause_linux(u["username"])
                except Exception:
                    log.exception("pause failed for %s",u["username"])
                c.execute("UPDATE users SET paused=1,status='Expired' WHERE id=?",(u["id"],))
                changed=True
        c.commit()
    if changed:
        restart_proxy()

def main():
    init_db(Config.DB_PATH)
    while True:
        try:
            tick()
        except Exception:
            log.exception("accounting tick failed")
        time.sleep(INTERVAL)

if __name__=="__main__":
    main()
