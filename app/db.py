import sqlite3
from contextlib import contextmanager
from pathlib import Path

_DB = None

def init_db(path):
    global _DB
    _DB = path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        PRAGMA foreign_keys=ON;

        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY,
          username TEXT UNIQUE NOT NULL,
          password TEXT NOT NULL,
          limit_gb REAL NOT NULL DEFAULT 0,
          used_gb REAL NOT NULL DEFAULT 0,
          expire_date TEXT,
          status TEXT NOT NULL DEFAULT 'Active',
          paused INTEGER NOT NULL DEFAULT 0,
          initial_gb REAL NOT NULL DEFAULT 0,
          initial_days INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS user_protocols(
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          protocol TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1,
          identifier TEXT,
          config_json TEXT NOT NULL DEFAULT '{}',
          PRIMARY KEY(user_id, protocol)
        );

        CREATE TABLE IF NOT EXISTS protocol_usage(
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          protocol TEXT NOT NULL,
          rx_bytes INTEGER NOT NULL DEFAULT 0,
          tx_bytes INTEGER NOT NULL DEFAULT 0,
          last_rx_counter INTEGER NOT NULL DEFAULT 0,
          last_tx_counter INTEGER NOT NULL DEFAULT 0,
          online INTEGER NOT NULL DEFAULT 0,
          last_seen INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(user_id, protocol)
        );

        CREATE INDEX IF NOT EXISTS idx_users_state
          ON users(status, paused, expire_date);
        CREATE INDEX IF NOT EXISTS idx_protocol_identifier
          ON user_protocols(protocol, identifier);
        """)

        # Migrate older DBs that don't have identifier.
        cols = {r["name"] for r in c.execute("PRAGMA table_info(user_protocols)")}
        if "identifier" not in cols:
            c.execute("ALTER TABLE user_protocols ADD COLUMN identifier TEXT")

        c.commit()

@contextmanager
def connect():
    if not _DB:
        raise RuntimeError("database not initialized")
    c = sqlite3.connect(_DB, timeout=15, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA busy_timeout=15000")
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
    finally:
        c.close()
