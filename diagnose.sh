#!/usr/bin/env bash
set -u

APP=/etc/custom-panel

echo "=== Repository ==="
test -f "$APP/app/__init__.py" && echo "app package: OK" || echo "app package: MISSING"
test -f "$APP/.env" && echo ".env: OK" || echo ".env: MISSING"

echo
echo "=== Permissions ==="
namei -l "$APP" || true
ls -ld "$APP" "$APP/app" "$APP/data" "$APP/runtime" /run/custom-panel 2>/dev/null || true

echo
echo "=== Service identities ==="
id custompanel || true
id panelproxy || true

echo
echo "=== Python imports ==="
if [[ -f "$APP/.env" ]]; then
  set -a
  source "$APP/.env"
  set +a
  runuser -u panelproxy -- env PYTHONPATH="$APP" \
    CUSTOM_PANEL_SECRET_KEY="$CUSTOM_PANEL_SECRET_KEY" \
    CUSTOM_PANEL_ADMIN_USERNAME="$CUSTOM_PANEL_ADMIN_USERNAME" \
    CUSTOM_PANEL_ADMIN_PASSWORD_HASH="$CUSTOM_PANEL_ADMIN_PASSWORD_HASH" \
    CUSTOM_PANEL_DATA_KEY="$CUSTOM_PANEL_DATA_KEY" \
    CUSTOM_PANEL_DB="$CUSTOM_PANEL_DB" \
    CUSTOM_PANEL_SERVER_HOST="$CUSTOM_PANEL_SERVER_HOST" \
    CUSTOM_PANEL_INTERNAL_SSH_PORT="$CUSTOM_PANEL_INTERNAL_SSH_PORT" \
    CUSTOM_PANEL_PORT_START="$CUSTOM_PANEL_PORT_START" \
    CUSTOM_PANEL_PORT_END="$CUSTOM_PANEL_PORT_END" \
    CUSTOM_PANEL_HELPER_SOCKET="$CUSTOM_PANEL_HELPER_SOCKET" \
    "$APP/venv/bin/python" -c "import app.proxy_runtime; print('proxy import: OK')" || true
fi

echo
echo "=== Services ==="
for service in ssh custom-panel-helper custom-panel-proxy custom-panel-accounting custom-panel; do
  echo "--- $service ---"
  systemctl status "$service" --no-pager -l || true
done

echo
echo "=== Listening ports ==="
ss -lntp || true

echo
echo "=== Recent logs ==="
for service in custom-panel-helper custom-panel-proxy custom-panel-accounting custom-panel; do
  echo "--- $service ---"
  journalctl -u "$service" -n 80 --no-pager || true
done
