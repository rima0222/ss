# Custom Panel v7 Final — OpenSSH

This release uses **OpenSSH only**. OpenSSH is the preferred choice for Ubuntu
because it is mature, actively maintained, widely audited, integrated with
systemd/PAM, and avoids running extra SSH daemons.

## v7 Final fixes

- Fixes `status=200/CHDIR` and `Permission denied` for `panelproxy`.
- Assigns `panelproxy` to the `custompanel` group.
- Keeps application code root-owned and read-only.
- Makes only data, backup, and runtime directories group-writable.
- Verifies service-user permissions before starting services.
- Adds dynamic proxy reconciliation every two seconds.
- Creating, pausing, resuming, restoring, or deleting a user no longer calls
  `systemctl restart`.
- Existing connections continue while unrelated users are changed.
- Traffic is flushed to SQLite every three seconds.
- Passwords are encrypted at rest.
- The web panel and traffic proxy run without root privileges.
- Only the minimal account helper runs as root.

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
sudo systemctl status custom-panel-helper --no-pager
sudo systemctl status custom-panel-proxy --no-pager
sudo systemctl status custom-panel-accounting --no-pager
sudo systemctl status custom-panel --no-pager
```

## Accounting model

Each user receives a dedicated public port in the range `20000-29999`.
All bytes passing through that port are counted before forwarding to the
internal OpenSSH listener. Online status represents an active connection to
that assigned endpoint.

Static Shell and Python syntax checks are included in the release process.
A real connection and load test still has to be performed on the target VPS.
