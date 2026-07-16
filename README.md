# Custom Panel v11 — OpenSSH + SSH WebSocket

v11 uses one unprivileged service account (`custompanel`) for the web panel,
async proxy, accounting worker and SQLite database. The privileged Linux-account
helper remains isolated as root.

This prevents cross-user SQLite permission conflicts and fixes:

```text
attempt to write a readonly database
```

## Do OpenSSH and SSH WebSocket conflict?

No. They use different public endpoints and both forward to the same internal
OpenSSH server:

```text
OpenSSH user port 20000-24999 ─┐
                               ├─> internal OpenSSH :2222
WebSocket port 25000-29999 ────┘
```

The proxy tracks TCP and WebSocket online state separately and combines their
RX/TX values for the user's total traffic.

## Features

- OpenSSH TCP
- SSH WebSocket
- Enable either or both per user
- Add, edit, pause, resume and delete
- Change password, quota and remaining days
- Accurate endpoint RX/TX accounting
- Separate TCP/WS online status
- Automatic quota/time suspension
- Backup and restore
- Encrypted user passwords
- Hashed panel administrator password
- Login rate limiting
- One asyncio proxy process
- One Gunicorn worker
- Dark responsive dashboard

## Install

Upload all ZIP contents to the root of the GitHub repository, then run:

```bash
curl -fsSL https://raw.githubusercontent.com/rima0222/ss/main/install.sh -o /tmp/install.sh
bash -n /tmp/install.sh
sudo bash /tmp/install.sh
```

The installer performs an SQLite write test before starting services and a
second health check after startup.

## Credentials

```bash
sudo bash /etc/custom-panel/show-credentials.sh
```

Change administrator password:

```bash
sudo bash /etc/custom-panel/reset-admin-password.sh 'NEW_STRONG_PASSWORD'
```

## Diagnostics

```bash
sudo bash /etc/custom-panel/diagnose.sh
```

## Ports

- Panel: 5000/tcp
- OpenSSH endpoints: 20000-24999/tcp
- WebSocket endpoints: 25000-29999/tcp

Static Shell and Python syntax validation has been completed. Real client and
load tests must still be performed on the target VPS.
