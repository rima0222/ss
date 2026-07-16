import json
import logging
import subprocess
import time
from datetime import date

from app.config import Config
from app.db import connect, init_db
from app.system_accounts import pause as pause_linux

INTERVAL = 10
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("custom-panel-accounting")

def run(args):
    return subprocess.run(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
        check=False,
    )

def ssh_online_users():
    result = run(["ps", "-eo", "user=,comm="])
    users = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == "sshd":
            if parts[0] not in {"root", "sshd", "nobody"}:
                users.add(parts[0])
    return users

def xray_stats(reset=True):
    args = [
        "/usr/local/bin/xray", "api", "statsquery",
        f"--server={Config.XRAY_API}",
    ]
    if reset:
        args.append("-reset=true")
    result = run(args)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "xray stats query failed")
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return {}
    return {
        item.get("name"): int(item.get("value", 0))
        for item in payload.get("stat", [])
        if item.get("name")
    }

def tick():
    now = int(time.time())
    ssh_online = ssh_online_users()
    stats = xray_stats(reset=True)

    with connect() as conn:
        users = [dict(row) for row in conn.execute("SELECT * FROM users").fetchall()]

        for user in users:
            ssh_state = int(user["username"] in ssh_online)

            up_name = f"user>>>{user['xray_email']}>>>traffic>>>uplink"
            down_name = f"user>>>{user['xray_email']}>>>traffic>>>downlink"
            online_name = f"user>>>{user['xray_email']}>>>online"

            up = stats.get(up_name, 0) if user["xray_enabled"] else 0
            down = stats.get(down_name, 0) if user["xray_enabled"] else 0
            xray_online = int(stats.get(online_name, 0) > 0) if user["xray_enabled"] else 0

            conn.execute("""
            UPDATE users
            SET ssh_online=?,
                xray_online=?,
                last_seen_ssh=CASE WHEN ?=1 THEN ? ELSE last_seen_ssh END,
                last_seen_xray=CASE WHEN ?=1 THEN ? ELSE last_seen_xray END,
                xray_rx_bytes=xray_rx_bytes+?,
                xray_tx_bytes=xray_tx_bytes+?,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """, (
                ssh_state, xray_online,
                ssh_state, now,
                xray_online, now,
                down, up, user["id"],
            ))

            used_gb = (
                int(user["xray_rx_bytes"] or 0)
                + int(user["xray_tx_bytes"] or 0)
                + down + up
            ) / (1024 ** 3)

            expired = False
            try:
                expired = date.fromisoformat(user["expire_date"]) < date.today()
            except Exception:
                pass

            over_quota = float(user["limit_gb"] or 0) > 0 and used_gb >= float(user["limit_gb"])
            if not user["paused"] and (expired or over_quota):
                if user["ssh_enabled"]:
                    try:
                        pause_linux(user["username"])
                    except Exception:
                        log.exception("Could not pause SSH user %s", user["username"])
                conn.execute("""
                UPDATE users SET paused=1,status='Expired',updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """, (user["id"],))

        conn.commit()

def main():
    init_db(Config.DB_PATH)
    log.info("Accounting worker started")
    while True:
        try:
            tick()
        except Exception:
            log.exception("Accounting tick failed")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
