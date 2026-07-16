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

## v1.1 update

- Multiple protocols can be created for one user in a single operation.
- Interrupted SSH user creation is recovered idempotently.
- WireGuard forwarding rules are added through UFW.
- WireGuard peers are restored automatically after reboot.
- Dashboard displays live online state plus WireGuard/OpenVPN receive and transmit counters.
- Existing installations update with the same one-line installer.

## v1.2 changes

- Removed live traffic counters from the dashboard.
- Shows remaining validity days instead of the raw expiry date.
- Robust Linux user creation using `useradd -N`, with recovery from leftover accounts/groups and useful stderr messages.

## Clean installation behavior

The one-line installer performs a clean reinstall by default:

```bash
curl -fsSL https://raw.githubusercontent.com/rima0222/ss/main/install.sh | sudo bash
```

Before cleanup, it creates an emergency rescue archive under:

```text
/root/custom-panel-rescue-YYYYMMDD-HHMMSS.tar.gz
```

The cleanup removes only Custom Panel services, its database/application directory,
its `wg0`, OpenVPN server configuration, Custom Panel strongSwan fragments, and users
listed in the panel database. Protected accounts such as `root` and `ubuntu` are never removed.
The primary OpenSSH server configuration is not rewritten.

To update without cleaning the existing installation:

```bash
curl -fsSL https://raw.githubusercontent.com/rima0222/ss/main/install.sh \
  | sudo env CUSTOM_PANEL_CLEAN_INSTALL=0 bash
```

## v1.4 passwd lock fix

- Removes `ProtectSystem=full`, which prevented `useradd` from creating `/etc/passwd.lock`.
- Sets `ProtectSystem=no` because the panel intentionally manages Linux accounts.
- Serializes `useradd`, `usermod`, `chpasswd`, and `userdel` with `/run/lock/custom-panel-accounts.lock` across Gunicorn workers.
