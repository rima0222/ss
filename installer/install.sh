#!/bin/bash
set -e

APP_DIR="/opt/custom-panel"
DATA_DIR="/var/lib/custom-panel"

echo "[*] Custom Panel v15 installer"

# cleanup old panel state
systemctl stop custom-panel.service 2>/dev/null || true
systemctl stop custom-panel-agent.service 2>/dev/null || true

systemctl disable custom-panel.service 2>/dev/null || true
systemctl disable custom-panel-agent.service 2>/dev/null || true

rm -f /etc/systemd/system/custom-panel*.service
systemctl daemon-reload

rm -rf "$DATA_DIR"
rm -rf /run/custom-panel

mkdir -p "$APP_DIR"
mkdir -p "$DATA_DIR"

# requirements
apt update -y
apt install -y python3 python3-venv python3-pip sqlite3 openssh-server nftables

python3 -m venv "$APP_DIR/venv"

# create fresh admin
ADMIN_USER="admin"
ADMIN_PASS=$(openssl rand -base64 24 | tr -d '/+=')

mkdir -p /etc/custom-panel

cat > /etc/custom-panel/admin-credentials.txt <<EOF
Username: $ADMIN_USER
Password: $ADMIN_PASS
EOF

chmod 600 /etc/custom-panel/admin-credentials.txt

echo "[*] Creating systemd services"

cat >/etc/systemd/system/custom-panel.service <<EOF
[Unit]
Description=Custom Panel v15

[Service]
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python3 $APP_DIR/panel/app.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/custom-panel-agent.service <<EOF
[Unit]
Description=Custom Panel v15 Agent

[Service]
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python3 $APP_DIR/agent/session_monitor.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable custom-panel.service custom-panel-agent.service
systemctl start custom-panel.service custom-panel-agent.service || true

echo ""
echo "================================"
echo "Installed Custom Panel v15"
echo "Credentials:"
cat /etc/custom-panel/admin-credentials.txt
echo "================================"
