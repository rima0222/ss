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
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT UNIQUE NOT NULL,
          password TEXT NOT NULL,
          limit_gb REAL NOT NULL DEFAULT 0,
          expire_date TEXT,
          paused INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'Active',

          openssh_enabled INTEGER NOT NULL DEFAULT 1,
          dropbear_enabled INTEGER NOT NULL DEFAULT 0,
          ws_enabled INTEGER NOT NULL DEFAULT 0,
          tls_enabled INTEGER NOT NULL DEFAULT 0,

          openssh_port INTEGER UNIQUE,
          dropbear_port INTEGER UNIQUE,
          ws_port INTEGER UNIQUE,
          tls_port INTEGER UNIQUE,
          ws_token TEXT,

          rx_bytes INTEGER NOT NULL DEFAULT 0,
          tx_bytes INTEGER NOT NULL DEFAULT 0,
          online_count INTEGER NOT NULL DEFAULT 0,
          last_seen INTEGER NOT NULL DEFAULT 0,

          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS transport_usage(
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          transport TEXT NOT NULL,
          rx_bytes INTEGER NOT NULL DEFAULT 0,
          tx_bytes INTEGER NOT NULL DEFAULT 0,
          online INTEGER NOT NULL DEFAULT 0,
          last_seen INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(user_id, transport)
        );

        CREATE INDEX IF NOT EXISTS idx_users_state ON users(paused,status,expire_date);
        """)
        c.commit()

@contextmanager
def connect():
    if not _DB:
        raise RuntimeError("database not initialized")
    c = sqlite3.connect(_DB, timeout=20, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA busy_timeout=20000")
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
    finally:
        c.close()
