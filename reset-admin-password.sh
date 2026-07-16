#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="/etc/custom-panel"
[[ "$EUID" -eq 0 ]] || { echo "Run as root."; exit 1; }
NEW_PASSWORD="${1:-$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(18))
PY
)}"
sed -i "s|^CUSTOM_PANEL_ADMIN_PASSWORD=.*|CUSTOM_PANEL_ADMIN_PASSWORD=$NEW_PASSWORD|" "$APP_DIR/.env"
USERNAME="$(grep '^CUSTOM_PANEL_ADMIN_USERNAME=' "$APP_DIR/.env" | cut -d= -f2-)"
printf 'Username: %s\nPassword: %s\n' "${USERNAME:-admin}" "$NEW_PASSWORD" > "$APP_DIR/admin-credentials.txt"
chmod 600 "$APP_DIR/.env" "$APP_DIR/admin-credentials.txt"
systemctl restart custom-panel
cat "$APP_DIR/admin-credentials.txt"
