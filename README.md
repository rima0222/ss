# Custom Panel v12 — Live OpenSSH + WebSocket Accounting

v12 replaces the previous dashboard accounting path.

## Why v11 could show Offline and 0 B

The proxy kept counters in memory and the panel only read SQLite. If a database
flush was delayed or failed, the connection continued working but the panel
could still display Offline and zero traffic.

## v12 accounting

The proxy now produces two outputs:

1. A live atomic snapshot at `/run/custom-panel/live.json`, updated every second.
2. Batched persistent SQLite counters with retry handling.

The API combines the saved SQLite total with the current unflushed byte delta.
Online status comes directly from the live proxy snapshot.

This gives:

- Online status within about one second.
- Traffic updates within about one second.
- Persistent totals after restart.
- Low SQLite write frequency.
- No process scan, `who`, `ss`, `netstat`, iptables accounting or per-user worker.

## Protocol isolation

OpenSSH TCP and SSH WebSocket use separate public endpoint ranges:

- OpenSSH: `20000-24999/tcp`
- WebSocket: `25000-29999/tcp`

Both forward to internal OpenSSH on port 2222 and do not bind the same public
port, so they do not conflict.

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

The diagnostic output includes the live JSON snapshot and stored database
counters.

Shell and Python syntax are validated. Real OpenSSH and WebSocket traffic must
still be tested on the target VPS.
