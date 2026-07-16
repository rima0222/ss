#!/bin/bash
set -e

APP=/opt/custom-panel
STATE=/var/lib/custom-panel

echo "[*] Custom Panel v16 installation"

systemctl stop custom-panel.service 2>/dev/null || true
systemctl stop custom-panel-agent.service 2>/dev/null || true

systemctl disable custom-panel.service 2>/dev/null || true
systemctl disable custom-panel-agent.service 2>/dev/null || true

rm -f /etc/systemd/system/custom-panel*.service
systemctl daemon-reload

rm -rf $STATE
rm -rf /run/custom-panel

mkdir -p $APP
mkdir -p /etc/custom-panel

apt update -y
apt install -y python3 python3-venv python3-pip sqlite3 openssh-server nftables

python3 -m venv $APP/venv

PASS=$(openssl rand -base64 32 | tr -d '/+=')

cat >/etc/custom-panel/admin-credentials.txt <<EOF
Username: admin
Password: $PASS
EOF

chmod 600 /etc/custom-panel/admin-credentials.txt

cat >/etc/systemd/system/custom-panel.service <<EOF
[Unit]
Description=Custom Panel v16

[Service]
WorkingDirectory=$APP
ExecStart=$APP/venv/bin/python3 $APP/panel/app.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/custom-panel-agent.service <<EOF
[Unit]
Description=Custom Panel v16 Agent

[Service]
WorkingDirectory=$APP
ExecStart=$APP/venv/bin/python3 $APP/agent/main.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable custom-panel custom-panel-agent
systemctl start custom-panel custom-panel-agent || true

echo "================================"
echo "Custom Panel v16 Installed"
cat /etc/custom-panel/admin-credentials.txt
echo "================================"
