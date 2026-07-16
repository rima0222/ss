# Custom Panel Complete

A modular Ubuntu control panel for account lifecycle, quotas, expiry, pause/resume,
legacy-compatible backup/restore, server statistics, SSH, WireGuard, OpenVPN and IKEv2 metadata.

## Install

Install on Ubuntu 24.04 with one command:

```bash
curl -fsSL https://raw.githubusercontent.com/rima0222/ss/main/install.sh | sudo bash
```

Credentials are written to:

```bash
sudo cat /etc/custom-panel/admin-credentials.txt
```

## Protocol status

- SSH: operational.
- WireGuard: operational after installer creates `wg0`.
- OpenVPN: server bootstrap and per-user inline client profiles are included.
- IKEv2: strongSwan bootstrap and EAP user secrets are included; clients must trust the generated CA certificate.

The installer auto-detects the public IPv4 address. For a domain, set `PANEL_SERVER_HOST`
before running the installer.

## Backup

Restore accepts both the old list-shaped JSON backup and the new versioned format.
