#!/usr/bin/env bash
set -u
APP=/etc/custom-panel
echo "=== Files ==="
find "$APP" -maxdepth 2 -type f | sort || true
echo "=== Identities ==="
id custompanel || true
id panelproxy || true
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
