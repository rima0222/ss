# Custom Panel — OpenSSH + SSH WebSocket

A lightweight SSH panel for Ubuntu 22.04 and 24.04.

## Features

- OpenSSH TCP and SSH WebSocket.
- User-specific TCP and WebSocket endpoints.
- Accurate RX/TX accounting per endpoint.
- Real online status for TCP and WebSocket separately.
- Add, edit, pause, resume and delete users.
- Change user password, quota and remaining days.
- Enable or disable TCP/WS per user.
- Automatic quota and time enforcement.
- JSON backup and restore.
- Encrypted user passwords at rest.
- Hashed panel administrator password.
- Login rate limiting.
- One asyncio proxy process and one Gunicorn worker.
- Designed for low-memory VPS servers.

## Install

Upload these files directly to the root of your GitHub repository.

```bash
curl -fsSL https://raw.githubusercontent.com/rima0222/ss/main/install.sh -o /tmp/install.sh
bash -n /tmp/install.sh
sudo bash /tmp/install.sh
```

## Panel credentials

```bash
sudo bash /etc/custom-panel/show-credentials.sh
```

Change the panel administrator password:

```bash
sudo bash /etc/custom-panel/reset-admin-password.sh 'NEW_STRONG_PASSWORD'
```

## Diagnostics

```bash
sudo bash /etc/custom-panel/diagnose.sh
```

## Ports

- Panel: 5000/tcp
- User OpenSSH endpoints: 20000-24999/tcp
- User WebSocket endpoints: 25000-29999/tcp

Each user must use the endpoint assigned to that account. Traffic is attributed
to the endpoint because the SSH username is inside the encrypted SSH session.

Shell and Python syntax are validated in the release build. Actual SSH and
WebSocket client tests must be performed after installation on the target VPS.
