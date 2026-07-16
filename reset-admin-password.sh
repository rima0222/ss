#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/etc/custom-panel"
ENV_FILE="$APP_DIR/.env"
CREDS_FILE="$APP_DIR/admin-credentials.txt"

if [[ "$EUID" -ne 0 ]]; then
  echo "Run as root: sudo bash reset-admin-password.sh"
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Panel environment file not found: $ENV_FILE"
  exit 1
fi

NEW_PASSWORD="${1:-}"
if [[ -z "$NEW_PASSWORD" ]]; then
  NEW_PASSWORD="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(18))
PY
)"
fi

ADMIN_USERNAME="$(grep '^CUSTOM_PANEL_ADMIN_USERNAME=' "$ENV_FILE" | cut -d= -f2- || true)"
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"

if grep -q '^CUSTOM_PANEL_ADMIN_PASSWORD=' "$ENV_FILE"; then
  sed -i "s|^CUSTOM_PANEL_ADMIN_PASSWORD=.*$|CUSTOM_PANEL_ADMIN_PASSWORD=$NEW_PASSWORD|" "$ENV_FILE"
else
  printf '\nCUSTOM_PANEL_ADMIN_PASSWORD=%s\n' "$NEW_PASSWORD" >> "$ENV_FILE"
fi

printf 'Username: %s\nPassword: %s\n' "$ADMIN_USERNAME" "$NEW_PASSWORD" > "$CREDS_FILE"
chmod 600 "$ENV_FILE" "$CREDS_FILE"

systemctl restart custom-panel
echo "Admin password updated."
cat "$CREDS_FILE"
