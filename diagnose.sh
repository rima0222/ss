#!/usr/bin/env bash
set -u
APP=/etc/custom-panel
echo "=== Files ==="
find "$APP" -maxdepth 2 -type f | sort || true
echo "=== Identities ==="
id custompanel || true
echo "=== Permissions ==="
namei -l "$APP" || true
ls -ld "$APP" "$APP/data" /run/custom-panel || true
echo "=== Services ==="
for s in ssh custom-panel-helper custom-panel-proxy custom-panel-accounting custom-panel; do
  systemctl status "$s" --no-pager -l || true
done
echo "=== Logs ==="
for s in custom-panel-helper custom-panel-proxy custom-panel-accounting custom-panel; do
  journalctl -u "$s" -n 100 --no-pager || true
done
echo "=== Ports ==="
ss -lntp || true


echo "=== SQLite write check ==="
if [[ -f "$APP/.env" ]]; then
  set -a
  source "$APP/.env"
  set +a
  runuser -u custompanel -- env PYTHONPATH="$APP" \
    CUSTOM_PANEL_SECRET_KEY="$CUSTOM_PANEL_SECRET_KEY" \
    CUSTOM_PANEL_ADMIN_USERNAME="$CUSTOM_PANEL_ADMIN_USERNAME" \
    CUSTOM_PANEL_ADMIN_PASSWORD_HASH="$CUSTOM_PANEL_ADMIN_PASSWORD_HASH" \
    CUSTOM_PANEL_DATA_KEY="$CUSTOM_PANEL_DATA_KEY" \
    CUSTOM_PANEL_DB="$CUSTOM_PANEL_DB" \
    CUSTOM_PANEL_SERVER_HOST="$CUSTOM_PANEL_SERVER_HOST" \
    CUSTOM_PANEL_INTERNAL_SSH_PORT="$CUSTOM_PANEL_INTERNAL_SSH_PORT" \
    CUSTOM_PANEL_TCP_PORT_START="$CUSTOM_PANEL_TCP_PORT_START" \
    CUSTOM_PANEL_TCP_PORT_END="$CUSTOM_PANEL_TCP_PORT_END" \
    CUSTOM_PANEL_WS_PORT_START="$CUSTOM_PANEL_WS_PORT_START" \
    CUSTOM_PANEL_WS_PORT_END="$CUSTOM_PANEL_WS_PORT_END" \
    CUSTOM_PANEL_HELPER_SOCKET="$CUSTOM_PANEL_HELPER_SOCKET" \
    "$APP/venv/bin/python" - <<'PY' || true
from app.config import Config
from app.db import init_db, connect
init_db(Config.DB_PATH)
with connect() as conn:
    conn.execute("CREATE TABLE IF NOT EXISTS diagnose_write_test(id INTEGER PRIMARY KEY)")
    conn.execute("INSERT OR REPLACE INTO diagnose_write_test(id) VALUES(1)")
    conn.commit()
    conn.execute("DROP TABLE diagnose_write_test")
    conn.commit()
print("SQLite writable: YES")
PY
fi
