CREATE TABLE users(
 id INTEGER PRIMARY KEY,
 username TEXT UNIQUE,
 password_hash TEXT,
 quota_bytes INTEGER DEFAULT 0,
 remaining_days INTEGER DEFAULT 0,
 paused INTEGER DEFAULT 0
);

CREATE TABLE sessions(
 id INTEGER PRIMARY KEY,
 user_id INTEGER,
 ip TEXT,
 started_at INTEGER,
 last_seen INTEGER,
 online INTEGER DEFAULT 1
);

CREATE TABLE traffic(
 id INTEGER PRIMARY KEY,
 user_id INTEGER,
 rx_bytes INTEGER DEFAULT 0,
 tx_bytes INTEGER DEFAULT 0,
 created_at INTEGER
);

CREATE TABLE admin(
 id INTEGER PRIMARY KEY,
 username TEXT,
 password_hash TEXT
);
