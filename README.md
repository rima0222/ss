# Custom Panel v1.5

Production-oriented Ubuntu panel for SSH, WireGuard and OpenVPN. IKEv2 has been removed because older releases generated an invalid strongSwan configuration.

## Features

- SSH, WireGuard and OpenVPN can be assigned to the same user
- User create/edit/pause/resume/delete
- Remaining days and quota display
- Online status
- WireGuard QR/config and OpenVPN `.ovpn` export
- Versioned backup/restore compatible with legacy backups
- Clean reinstall with emergency rescue archive
- Linux-account file lock for safe concurrent operations
- WireGuard/OpenVPN usage accounting every 15 seconds
- OpenVPN NAT, disabled-user enforcement and management disconnect

Old `ikev2` entries in backups or databases are ignored and removed safely.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/rima0222/ss/main/install.sh | sudo bash
```

Credentials:

```bash
sudo cat /etc/custom-panel/admin-credentials.txt
```

The clean installer saves an emergency archive under `/root/custom-panel-rescue-*.tar.gz`.
