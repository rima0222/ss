# Custom Panel v9 Final — OpenSSH Only

A lightweight OpenSSH panel for Ubuntu 22.04/24.04.

## Main capabilities

- One dedicated public SSH endpoint per user.
- Accurate RX/TX counting at the assigned endpoint.
- Real online state based on active endpoint connections.
- Pause, resume, edit, delete and reset traffic.
- Remaining days instead of expiry-date display.
- Automatic quota and time enforcement.
- JSON backup and restore.
- Encrypted user passwords at rest.
- Hashed administrator password.
- Dark responsive dashboard.
- One Gunicorn worker and one asyncio proxy process.

## v9 installer fixes

- All services receive an explicit `PYTHONPATH=/etc/custom-panel`.
- Python import tests run with the service user's identity and environment.
- Fixes `ModuleNotFoundError: No module named 'app'`.
- Verifies that the cloned repository contains all required files.
- Removes stale passwd lock files only when account tools are not running.
- Verifies permissions, service state, the login endpoint and panel listener.
- Provides a complete diagnostic script.

## Install

Upload the ZIP contents directly to the root of the GitHub repository, then run:

```bash
curl -fsSL https://raw.githubusercontent.com/rima0222/ss/main/install.sh -o /tmp/install.sh
bash -n /tmp/install.sh
sudo bash /tmp/install.sh
```

## Credentials

```bash
sudo bash /etc/custom-panel/show-credentials.sh
```

Set a custom administrator password:

```bash
sudo bash /etc/custom-panel/reset-admin-password.sh 'NEW_STRONG_PASSWORD'
```

## Diagnostics

```bash
sudo bash /etc/custom-panel/diagnose.sh
```

## Important accounting rule

Traffic belongs to the dedicated public port, not to the SSH username discovered
inside the encrypted connection. Each user must use the port assigned to that
account. Using another account's port attributes traffic to that endpoint.

Shell and Python syntax have been validated. Real SSH connection and load tests
must still be performed on the target VPS.
