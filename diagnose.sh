#!/usr/bin/env bash
set -u

echo "=== Permissions ==="
namei -l /etc/custom-panel || true
ls -ld /etc/custom-panel /etc/custom-panel/data /run/custom-panel || true

echo
echo "=== Identity ==="
id custompanel || true
id panelproxy || true

echo
echo "=== Services ==="
for service in custom-panel-helper custom-panel-proxy custom-panel-accounting custom-panel ssh; do
  echo "--- $service ---"
  systemctl status "$service" --no-pager -l || true
done

echo
echo "=== Recent logs ==="
for service in custom-panel-helper custom-panel-proxy custom-panel-accounting custom-panel; do
  echo "--- $service ---"
  journalctl -u "$service" -n 40 --no-pager || true
done
