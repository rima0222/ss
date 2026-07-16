#!/bin/bash
set -e

echo '[*] Custom Panel v16 Final installer'

systemctl stop custom-panel.service 2>/dev/null || true
systemctl stop custom-panel-agent.service 2>/dev/null || true

systemctl disable custom-panel.service 2>/dev/null || true
systemctl disable custom-panel-agent.service 2>/dev/null || true

rm -f /etc/systemd/system/custom-panel*.service
systemctl daemon-reload

rm -rf /var/lib/custom-panel
rm -rf /run/custom-panel

apt update -y
apt install -y python3 python3-venv sqlite3 openssl

mkdir -p /opt/custom-panel
mkdir -p /etc/custom-panel

PASS=$(openssl rand -hex 16)

cat >/etc/custom-panel/admin-credentials.txt <<EOF
Username: admin
Password: $PASS
EOF

chmod 600 /etc/custom-panel/admin-credentials.txt

echo '[*] Installing services'

cat >/etc/systemd/system/custom-panel.service <<EOF
[Unit]
Description=Custom Panel v16

[Service]
WorkingDirectory=/opt/custom-panel
ExecStart=/usr/bin/python3 /opt/custom-panel/panel/app.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/custom-panel-agent.service <<EOF
[Unit]
Description=Custom Panel Agent v16

[Service]
WorkingDirectory=/opt/custom-panel
ExecStart=/usr/bin/python3 /opt/custom-panel/agent/main.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable custom-panel custom-panel-agent
systemctl start custom-panel custom-panel-agent

echo '================================'
echo 'Custom Panel v16 Installed'
cat /etc/custom-panel/admin-credentials.txt
echo '================================'
