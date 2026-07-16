import json
import logging
import os
import time
from pathlib import Path

from app.config import Config
from app.db import init_db, connect
from app.live import wireguard_stats, openvpn_stats

STATE = Path("/etc/custom-panel/runtime/accounting-state.json")
INTERVAL = 10

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("custom-panel-accounting")


def load_state():
    try:
        raw = json.loads(STATE.read_text())
        return raw if isinstance(raw, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        log.exception("Could not load accounting state; starting with an empty state")
        return {}


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, separators=(",", ":")))
    os.replace(tmp, STATE)


def counters():
    data = {}

    for name, stat in wireguard_stats(Config.WG_INTERFACE).items():
        data.setdefault(name, {})["wireguard"] = (
            int(stat.get("rx_bytes", 0)) + int(stat.get("tx_bytes", 0))
        )

    for name, stat in openvpn_stats().items():
        data.setdefault(name, {})["openvpn"] = (
            int(stat.get("rx_bytes", 0)) + int(stat.get("tx_bytes", 0))
        )

    return data


def active_usernames():
    with connect() as conn:
        return {
            row["username"]
            for row in conn.execute("SELECT username FROM users").fetchall()
        }


def tick(state):
    current = counters()
    users = active_usernames()
    deltas = {}

    # Remove state belonging to deleted users.
    state = {
        key: value
        for key, value in state.items()
        if key.split(":", 1)[0] in users
    }

    for username, protocols in current.items():
        if username not in users:
            continue

        for protocol, value in protocols.items():
            key = f"{username}:{protocol}"
            value = max(0, int(value))

            # A newly observed peer/session starts at zero so already transferred
            # bytes are not silently discarded before the first worker sample.
            previous = max(0, int(state.get(key, 0)))

            if value >= previous:
                delta = value - previous
            else:
                # Counter reset after a protocol/service restart.
                delta = value

            if delta > 0:
                deltas[username] = deltas.get(username, 0) + delta

            state[key] = value

    if deltas:
        rows = [
            (byte_count / (1024 ** 3), username)
            for username, byte_count in deltas.items()
            if byte_count > 0
        ]
        with connect() as conn:
            conn.executemany(
                """
                UPDATE users
                SET used_gb = used_gb + ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE username = ? AND paused = 0
                """,
                rows,
            )
            conn.commit()
        log.info("Updated traffic for %d user(s)", len(rows))

    save_state(state)
    return state


def main():
    init_db(Config.DB_PATH)
    state = load_state()
    log.info("Accounting worker started; interval=%ss", INTERVAL)

    while True:
        try:
            state = tick(state)
        except Exception:
            log.exception("Accounting tick failed")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
