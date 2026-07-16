#!/bin/bash
set -e
systemctl stop custom-panel.service 2>/dev/null || true
systemctl stop custom-panel-agent.service 2>/dev/null || true
systemctl disable custom-panel.service 2>/dev/null || true
systemctl disable custom-panel-agent.service 2>/dev/null || true
rm -f /etc/systemd/system/custom-panel*.service
systemctl daemon-reload
rm -rf /var/lib/custom-panel
rm -rf /run/custom-panel
echo "Clean state completed"
