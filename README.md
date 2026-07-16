# Custom Panel v6 — Optimized SSH Only

This release supports only OpenSSH through a dedicated per-user external port.

## Optimized for a small VPS

- One Gunicorn worker with four threads.
- One asyncio proxy process for all user ports.
- Traffic counters are held in memory and written to SQLite every five seconds.
- SQLite uses WAL, NORMAL synchronous mode, memory temp storage, and a small cache.
- No WireGuard, OpenVPN, IKEv2, Xray, Dropbear, WebSocket, or TLS processes.
- Dashboard polling is once every five seconds.

## Accurate traffic and online state

Each user has a dedicated external TCP port. Every byte passing through that
port is counted before being forwarded to the internal OpenSSH service.

The online state is the number of active connections to that assigned endpoint.

## Remaining time

The database stores `remaining_days`, not an expiry date. The dashboard displays
only the number of days remaining.

## Capacity

A 1 GB VPS can typically handle hundreds of mostly idle accounts, but the real
limit depends on simultaneous encrypted SSH sessions, CPU, bandwidth, and what
users tunnel through the server. The installer raises the file descriptor limit,
but it does not promise a fixed number of concurrent sessions.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/rima0222/ss/main/install.sh -o /tmp/install.sh
bash -n /tmp/install.sh
sudo bash /tmp/install.sh
```
