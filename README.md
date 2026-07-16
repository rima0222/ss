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

## v1.6 OpenVPN and accounting fixes

- Removes the mandatory CRL file that prevented OpenVPN from starting.
- Protects the localhost OpenVPN management interface with a generated password.
- Stops installation if OpenVPN fails its health check.
- Logs accounting errors instead of silently discarding them.
- Counts a new WireGuard/OpenVPN counter from zero on first observation.
- Handles counter resets after protocol restarts.
- Refreshes each user's stored usage in the dashboard every 15 seconds.

Diagnostics:

```bash
sudo systemctl status openvpn-server@server --no-pager
sudo systemctl status custom-panel-accounting --no-pager
sudo journalctl -u custom-panel-accounting -n 100 --no-pager
sudo wg show wg0 transfer
```

Traffic accounting in this release covers WireGuard and OpenVPN. Linux SSH
sessions are not assigned fabricated traffic values.
