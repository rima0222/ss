# Custom Panel v13 — Enforced SSH Gateway

v13 changes the architecture so managed users cannot bypass accounting.

## Architecture

```text
OpenSSH TCP ports 20000-24999 ─┐
                               ├─> Async Gateway ─> OpenSSH 127.0.0.1:2222
WebSocket ports 25000-29999 ───┘

Server administration remains on normal SSH port 22.
```

Managed users are accepted only by the internal OpenSSH instance on localhost.
They must connect through their assigned TCP or WebSocket endpoint.

## Why this is more reliable

- Every managed byte crosses the gateway.
- Online state is the gateway's active connection count.
- A live atomic snapshot is updated every 0.5 seconds.
- SQLite persistence is batched every 2 seconds.
- The dashboard overlays pending bytes on stored totals.
- The dashboard displays `used / quota`.
- OpenSSH and WebSocket use separate listeners and cannot bind the same port.
- Direct port-22 access does not accept managed panel users through the internal
  panel SSH configuration.

## Features

- OpenSSH TCP and SSH WebSocket
- Add, edit, pause, resume and delete
- Change password, quota, remaining days and enabled methods
- Separate TCP/WS online state
- Accurate combined RX/TX
- Automatic quota and time suspension
- Backup and restore
- Change panel administrator username/password from the panel
- Encrypted user passwords and hashed administrator password
- One asyncio gateway process
- One Gunicorn worker

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

## Important client rule

Use the TCP port or WebSocket URL downloaded from the user's Config button.
Connecting to server port 22 bypasses the user's assigned gateway endpoint and
is reserved for server administration.

Static Shell and Python syntax have been validated. Real network and load tests
must be completed on the target VPS.
