import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
PRAGMA temp_store=MEMORY;
PRAGMA busy_timeout=20000;
PRAGMA wal_autocheckpoint=1000;

CREATE TABLE IF NOT EXISTS admins(
    id INTEGER PRIMARY KEY CHECK(id=1),
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    session_version INTEGER NOT NULL DEFAULT 1,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_enc TEXT NOT NULL,
    tcp_enabled INTEGER NOT NULL DEFAULT 1,
    ws_enabled INTEGER NOT NULL DEFAULT 1,
    tcp_port INTEGER UNIQUE,
    backend_port INTEGER NOT NULL UNIQUE,
    ws_token TEXT NOT NULL UNIQUE,
    quota_bytes INTEGER NOT NULL DEFAULT 0,
    download_bytes INTEGER NOT NULL DEFAULT 0,
    upload_bytes INTEGER NOT NULL DEFAULT 0,
    tcp_download_bytes INTEGER NOT NULL DEFAULT 0,
    tcp_upload_bytes INTEGER NOT NULL DEFAULT 0,
    ws_download_bytes INTEGER NOT NULL DEFAULT 0,
    ws_upload_bytes INTEGER NOT NULL DEFAULT 0,
    expires_at INTEGER NOT NULL,
    paused INTEGER NOT NULL DEFAULT 0,
    paused_at INTEGER,
    status TEXT NOT NULL DEFAULT 'active',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    subject TEXT,
    detail TEXT,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_active
ON users(paused, expires_at, status);

CREATE INDEX IF NOT EXISTS idx_users_ports
ON users(tcp_port, backend_port);
"""

def connect(path: str):
    conn = sqlite3.connect(path, timeout=20, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=20000")
    return conn

def initialize(path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()

@contextmanager
def transaction(path: str, immediate: bool = False):
    conn = connect(path)
    try:
        conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
