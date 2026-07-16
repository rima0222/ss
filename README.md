# Custom Panel v3 — SSH + Xray

A fresh Ubuntu panel supporting:

- SSH accounts
- Xray VMess users
- Xray per-user upload/download accounting
- Xray online status
- SSH online status
- pause/resume/edit/delete
- JSON backup and restore
- dark responsive frontend
- one-line GitHub installation

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/rima0222/ss/main/install.sh \
  -o /tmp/install.sh

bash -n /tmp/install.sh
sudo bash /tmp/install.sh
```

## Credentials

```bash
sudo bash /etc/custom-panel/show-credentials.sh
```

## Accuracy note

Xray traffic is collected from Xray's official Stats API using the per-user
email identifier and reset-based delta accounting.

SSH online state is read from active `sshd` processes. Exact per-user SSH
network-byte accounting is not included because OpenSSH does not expose a
native per-user traffic counter. The panel displays SSH traffic as `N/A`
instead of inventing a number.

## Ports

- 22/tcp: SSH
- 5000/tcp: panel
- 8443/tcp: Xray VMess
