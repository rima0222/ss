# Custom Panel v4 — SSH Suite

Supported transports:

- OpenSSH
- Dropbear
- SSH WebSocket
- SSH TLS

Each user receives dedicated external endpoints. Traffic is counted in the
proxy layer as exact RX/TX for that assigned endpoint, and online status is
based on active proxy connections.

## Important limitation

The byte counter is exact for traffic passing through the assigned per-user
port/path. Raw TCP SSH itself does not reveal the authenticated username to the
proxy before encryption/authentication, so users must use their own assigned
endpoint. Sharing another user's endpoint would attribute traffic to that
endpoint owner.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/rima0222/ss/main/install.sh -o /tmp/install.sh
bash -n /tmp/install.sh
sudo bash /tmp/install.sh
```

## Ports

- Panel: 5000/tcp
- Per-user OpenSSH: 20000-24999/tcp
- Per-user Dropbear: 25000-29999/tcp
- Per-user WebSocket: 30000-34999/tcp
- Per-user TLS: 35000-39999/tcp

## Credentials

```bash
sudo bash /etc/custom-panel/show-credentials.sh
```
