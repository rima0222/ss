# Custom Panel v2.1 — SSH + IKEv2

This release intentionally supports only:

- SSH
- IKEv2 / strongSwan

## Online status

- SSH: detected from active `sshd` sessions.
- IKEv2: detected from active strongSwan IKE/CHILD SAs.

## Traffic accounting

- IKEv2: exact cumulative RX/TX from strongSwan CHILD_SA counters.
- SSH: online status is exact, but traffic is shown as `N/A`.

A trustworthy per-user SSH traffic counter requires an eBPF/cgroup collector or
a separate network namespace for every SSH user. This release does not use the
old `/proc/PID/net/dev` method because it can attribute namespace-wide traffic
to the wrong user.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/rima0222/ss/main/install.sh | sudo bash
```

## Credentials

```bash
sudo bash /etc/custom-panel/show-credentials.sh
```

Reset to a random password:

```bash
sudo bash /etc/custom-panel/reset-admin-password.sh
```

## Diagnostics

```bash
sudo systemctl status custom-panel --no-pager
sudo systemctl status custom-panel-accounting --no-pager
sudo systemctl status strongswan --no-pager
sudo swanctl --list-sas
sudo journalctl -u custom-panel-accounting -n 100 --no-pager
```

## v2.1.1 installer fix

This release removes the orphaned WireGuard systemd unit body that caused:

```text
bash: [Unit]: command not found
```

It also removes residual WireGuard/OpenVPN routes, services, Python modules and
dependencies. The installer now verifies strongSwan, accounting and the web panel
before printing the final Installed message.

The `plugin ... failed to load` lines printed by `swanctl` are optional plugin
warnings. The relevant success lines are:

```text
loaded connection 'custom-panel-eap'
successfully loaded 1 connections
```
