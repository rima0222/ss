import logging
import time

from app.config import Config
from app.db import connect, init_db
from app.live import ikev2_counters, ssh_online

INTERVAL = 10
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("custom-panel-accounting")

def mappings():
    with connect() as c:
        rows = c.execute("""
        SELECT p.user_id,p.protocol,p.identifier,u.username,u.paused
        FROM user_protocols p
        JOIN users u ON u.id=p.user_id
        WHERE p.enabled=1 AND p.protocol IN ('ssh','ikev2')
        """).fetchall()
    return [dict(r) for r in rows]

def tick():
    now = int(time.time())
    ssh_users = ssh_online()
    ike = ikev2_counters()

    with connect() as c:
        for item in mappings():
            uid = item["user_id"]
            protocol = item["protocol"]
            username = item["username"]
            identifier = item["identifier"] or username

            if protocol == "ssh":
                online = int(username in ssh_users)
                c.execute("""
                INSERT INTO protocol_usage(user_id,protocol,online,last_seen,updated_at)
                VALUES(?,?,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(user_id,protocol) DO UPDATE SET
                  online=excluded.online,
                  last_seen=excluded.last_seen,
                  updated_at=CURRENT_TIMESTAMP
                """, (uid, "ssh", online, now if online else 0))
                continue

            counter = ike.get(identifier)
            if counter is None:
                c.execute("""
                INSERT INTO protocol_usage(user_id,protocol,online,updated_at)
                VALUES(?,?,0,CURRENT_TIMESTAMP)
                ON CONFLICT(user_id,protocol) DO UPDATE SET
                  online=0,
                  updated_at=CURRENT_TIMESTAMP
                """, (uid, "ikev2"))
                continue

            old = c.execute("""
            SELECT last_rx_counter,last_tx_counter
            FROM protocol_usage
            WHERE user_id=? AND protocol='ikev2'
            """, (uid,)).fetchone()

            old_rx = int(old["last_rx_counter"]) if old else 0
            old_tx = int(old["last_tx_counter"]) if old else 0
            new_rx = max(0, int(counter.get("rx", 0)))
            new_tx = max(0, int(counter.get("tx", 0)))

            delta_rx = new_rx - old_rx if new_rx >= old_rx else new_rx
            delta_tx = new_tx - old_tx if new_tx >= old_tx else new_tx

            c.execute("""
            INSERT INTO protocol_usage(
              user_id,protocol,rx_bytes,tx_bytes,last_rx_counter,last_tx_counter,
              online,last_seen,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(user_id,protocol) DO UPDATE SET
              rx_bytes=protocol_usage.rx_bytes+excluded.rx_bytes,
              tx_bytes=protocol_usage.tx_bytes+excluded.tx_bytes,
              last_rx_counter=excluded.last_rx_counter,
              last_tx_counter=excluded.last_tx_counter,
              online=1,
              last_seen=excluded.last_seen,
              updated_at=CURRENT_TIMESTAMP
            """, (
                uid, "ikev2",
                max(0, delta_rx), max(0, delta_tx),
                new_rx, new_tx,
                1, int(counter.get("seen") or now),
            ))

        # Only IKEv2 contributes exact bytes. SSH is intentionally excluded.
        c.execute("""
        UPDATE users
        SET used_gb = COALESCE((
          SELECT SUM(rx_bytes + tx_bytes) / 1073741824.0
          FROM protocol_usage pu
          WHERE pu.user_id=users.id AND pu.protocol='ikev2'
        ), 0),
        updated_at=CURRENT_TIMESTAMP
        """)
        c.commit()

def main():
    init_db(Config.DB_PATH)
    log.info("SSH/IKEv2 accounting worker started; interval=%ss", INTERVAL)
    while True:
        try:
            tick()
        except Exception:
            log.exception("Accounting tick failed")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
