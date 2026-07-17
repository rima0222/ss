#!/usr/bin/env bash
set -u
echo "=== Services ==="
for s in ssh custom-panel-sshd custom-panel-helper custom-panel-manager custom-panel-gateway custom-panel-web; do
  systemctl status "$s" --no-pager -l || true
done
echo "=== Ports ==="
ss -lntp || true
echo "=== Managed users ==="
getent group cpusers || true
getent passwd | awk -F: '$5=="custom-panel-managed"{print $1,$7}' || true
echo "=== Manager ==="
set -a
. /etc/custom-panel/panel.env 2>/dev/null || true
set +a
runuser -u custompanel -- env PYTHONPATH=/opt/custom-panel \
  /opt/custom-panel/venv/bin/python -m custom_panel.cli health || true
echo "=== Logs ==="
for s in custom-panel-sshd custom-panel-helper custom-panel-manager custom-panel-gateway custom-panel-web; do
  echo "--- $s ---"; journalctl -u "$s" -n 80 --no-pager || true
done
