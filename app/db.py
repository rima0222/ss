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
        PRAGMA temp_store=MEMORY;
        PRAGMA cache_size=-16000;

        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT UNIQUE NOT NULL,
          password TEXT NOT NULL,
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

        CREATE INDEX IF NOT EXISTS idx_users_runtime
          ON users(paused,status,remaining_days);
        CREATE INDEX IF NOT EXISTS idx_users_port ON users(port);
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
