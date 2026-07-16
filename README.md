# Custom Panel v8 Stable — OpenSSH Only

v8 removes the systemd mount-namespace directives that caused:

```text
status=200/CHDIR
status=226/NAMESPACE
Failed to set up mount namespacing
```

## Architecture

- OpenSSH only.
- One unprivileged web service.
- One unprivileged asyncio traffic proxy.
- One unprivileged accounting worker.
- One minimal root account helper.
- Per-user public ports from 20000 to 29999.
- Batched SQLite accounting.
- Encrypted user passwords at rest.
- Hashed panel administrator password.
- Persistent remaining-day calculation.
- Backup and restore.

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

## Diagnostics

```bash
sudo bash /etc/custom-panel/diagnose.sh
```

## Important accounting rule

Traffic is attributed to the user's dedicated public port. A user must connect
through the port assigned to that account. The proxy counts every byte before
forwarding the encrypted connection to OpenSSH.

Static Shell and Python syntax checks were completed. Real network, accounting,
and concurrent-load tests must be performed on the target VPS.
