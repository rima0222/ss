# Custom Panel v14 — Engineered Session Gateway

v14 replaces the old online/traffic subsystem while preserving the existing
panel features.

## New accounting design

The Gateway owns an in-memory session registry:

```text
Session ID
User
Endpoint type
Start time
Last activity
RX
TX
```

A user is online only while at least one Gateway session is open.

The Gateway writes:

- An atomic live snapshot every 0.5 seconds.
- Persistent traffic totals to SQLite every 3 seconds.
- Failed SQLite writes are retried and unsaved byte deltas are restored to
  memory instead of being lost.

The dashboard reads live session state and overlays unflushed bytes on the saved
database total.

## Connection architecture

```text
OpenSSH TCP 20000-24999 ─┐
                         ├─> Session Gateway ─> OpenSSH 127.0.0.1:2222
WebSocket 25000-29999 ───┘
```

The internal OpenSSH service is localhost-only. Managed users must use their
assigned TCP port or WebSocket URL.

## Preserved panel features

- Add, edit and delete users
- Pause and resume
- Change user password
- Change quota and remaining days
- Select TCP, WebSocket or both
- Reset traffic
- Backup and restore
- Download connection details
- Change panel administrator username and password from the panel
- Encrypted user passwords
- Hashed administrator password
- Dark responsive interface

## Fresh installation behavior

A normal v14 installation is clean:

- Previous panel services are stopped.
- `/etc/custom-panel` is removed.
- Previous panel database and administrator settings are removed.
- A new database and random initial administrator password are created.
- Old users return only when the administrator explicitly restores a backup.

## Resource model

- One asyncio Gateway process
- One Gunicorn worker
- One accounting worker
- No per-user processes
- WebSocket compression disabled
- 128 KiB relay buffers
- SQLite WAL with batched writes

Lower network latency mostly depends on server location, routing and congestion.
The Gateway avoids deliberate delays, but software cannot reduce the physical
network RTT below the route latency.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/rima0222/ss/main/install.sh -o /tmp/install.sh
bash -n /tmp/install.sh
sudo bash /tmp/install.sh
```

## Credentials

```bash
sudo bash /etc/custom-panel/show-credentials.sh
```

## Diagnostics

```bash
sudo bash /etc/custom-panel/diagnose.sh
```

Static Shell and Python syntax checks are included. Actual client and concurrent
load tests must be performed on the target VPS.
