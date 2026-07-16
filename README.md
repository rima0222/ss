# Custom Panel v7 — Secure Optimized SSH

OpenSSH-only panel designed for a small VPS and many mostly-idle users.

## Architecture

- Web panel runs as an unprivileged `custompanel` user.
- Linux account changes are performed by a minimal root helper over a protected Unix socket.
- Traffic proxy runs as the unprivileged `panelproxy` user.
- One asyncio process handles all per-user ports.
- Traffic is batched to SQLite every three seconds.
- User passwords are encrypted at rest with Fernet.
- Admin password is stored as a secure Werkzeug hash.
- Login attempts are rate limited.
- Remaining days use a persistent daily rollover, so service restarts do not reset the timer.

## Accurate traffic

Each user receives a dedicated port between 20000 and 29999. Every byte passing
through that endpoint is counted before forwarding to internal OpenSSH.

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

## Services

```bash
sudo systemctl status custom-panel-helper
sudo systemctl status custom-panel-proxy
sudo systemctl status custom-panel-accounting
sudo systemctl status custom-panel
```

Static syntax validation was performed, but real connection/load testing must be
done on the target VPS.
