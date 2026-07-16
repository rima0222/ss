import sqlite3
from contextlib import contextmanager
from pathlib import Path

_DB = None

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
PRAGMA temp_store=MEMORY;
PRAGMA cache_size=-12000;
PRAGMA wal_autocheckpoint=1000;

CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_enc TEXT NOT NULL,
  port INTEGER UNIQUE NOT NULL,
  limit_bytes INTEGER NOT NULL DEFAULT 0,
  remaining_days INTEGER NOT NULL DEFAULT 30,
  paused INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'Active',
  rx_bytes INTEGER NOT NULL DEFAULT 0,
  tx_bytes INTEGER NOT NULL DEFAULT 0,
  online INTEGER NOT NULL DEFAULT 0,
  last_seen INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS metadata(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_runtime
  ON users(paused,status,remaining_days);
CREATE INDEX IF NOT EXISTS idx_users_port
  ON users(port);
"""

def init_db(path):
    global _DB
    _DB = path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
        conn.commit()

@contextmanager
def connect():
    if not _DB:
        raise RuntimeError("database not initialized")
    conn = sqlite3.connect(_DB, timeout=20, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=20000")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()
