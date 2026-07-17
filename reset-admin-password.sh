#!/usr/bin/env bash
set -Eeuo pipefail
APP=/opt/custom-panel
ENV=/etc/custom-panel/panel.env
[[ $EUID -eq 0 ]] || { echo "Run as root"; exit 1; }
PASSWORD="${1:-$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(20))
PY
)}"
USERNAME="${2:-admin}"
set -a
. "$ENV"
set +a
runuser -u custompanel -- env PYTHONPATH="$APP" \
  "$APP/venv/bin/python" -m custom_panel.cli reset-admin \
  --username "$USERNAME" --password "$PASSWORD"
printf 'Username: %s\nPassword: %s\n' "$USERNAME" "$PASSWORD" > /etc/custom-panel/admin-credentials.txt
chmod 600 /etc/custom-panel/admin-credentials.txt
systemctl restart custom-panel-web
cat /etc/custom-panel/admin-credentials.txt
