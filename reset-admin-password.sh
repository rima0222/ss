#!/usr/bin/env bash
set -Eeuo pipefail
APP=/etc/custom-panel
[[ "$EUID" -eq 0 ]] || { echo "Run as root."; exit 1; }
PASS="${1:-$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(18))
PY
)}"
sed -i "s|^CUSTOM_PANEL_ADMIN_PASSWORD=.*|CUSTOM_PANEL_ADMIN_PASSWORD=$PASS|" "$APP/.env"
printf 'Username: admin\nPassword: %s\n' "$PASS" > "$APP/admin-credentials.txt"
chmod 600 "$APP/.env" "$APP/admin-credentials.txt"
systemctl restart custom-panel
cat "$APP/admin-credentials.txt"
