# Custom Panel v5 — SSH Suite

Supported methods:

- OpenSSH
- Dropbear
- SSH WebSocket
- SSH TLS

## Main fixes

- Linux account changes are serialized with a global lock.
- `useradd`, `usermod`, `chpasswd`, and `userdel` retry transient passwd-lock errors.
- The web service uses `ProtectSystem=no` because it intentionally manages Linux accounts.
- Dropbear runs as a dedicated `panel-dropbear.service` on localhost port 2223.
- Traffic and online status are measured by the per-user proxy endpoint.
- Backup includes users, ports, WebSocket tokens, counters, quota, and expiry.
- The dashboard has been redesigned with a consistent professional layout.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/rima0222/ss/main/install.sh -o /tmp/install.sh
bash -n /tmp/install.sh
sudo bash /tmp/install.sh
```

## Endpoint ranges

- OpenSSH: 20000–24999/tcp
- Dropbear: 25000–29999/tcp
- WebSocket: 30000–34999/tcp
- TLS: 35000–39999/tcp

Traffic is attributed to the assigned endpoint. Users must use their own endpoint.
