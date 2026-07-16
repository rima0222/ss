import sqlite3
from contextlib import contextmanager
from pathlib import Path

_DB_PATH = None

def init_db(path):
    global _DB_PATH
    _DB_PATH = path
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    with connect() as conn:
        conn.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        PRAGMA foreign_keys=ON;

        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT UNIQUE NOT NULL,
          password TEXT NOT NULL,
          limit_gb REAL NOT NULL DEFAULT 0,
          expire_date TEXT,
          paused INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'Active',
          ssh_enabled INTEGER NOT NULL DEFAULT 1,
          xray_enabled INTEGER NOT NULL DEFAULT 0,
          xray_uuid TEXT,
          xray_email TEXT,
          xray_rx_bytes INTEGER NOT NULL DEFAULT 0,
          xray_tx_bytes INTEGER NOT NULL DEFAULT 0,
          ssh_online INTEGER NOT NULL DEFAULT 0,
          xray_online INTEGER NOT NULL DEFAULT 0,
          last_seen_ssh INTEGER NOT NULL DEFAULT 0,
          last_seen_xray INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_users_status
          ON users(paused, status, expire_date);
        CREATE INDEX IF NOT EXISTS idx_users_xray_email
          ON users(xray_email);
        """)
        conn.commit()

@contextmanager
def connect():
    if not _DB_PATH:
        raise RuntimeError("database not initialized")
    conn = sqlite3.connect(_DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()
