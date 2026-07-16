#!/bin/bash
set -e

BASE=/opt/custom-panel

echo "[*] Installing Custom Panel"

mkdir -p $BASE
mkdir -p /etc/custom-panel
mkdir -p /var/lib/custom-panel

apt update -y
apt install -y python3 python3-venv python3-pip sqlite3 openssl

python3 -m venv $BASE/venv

PASS=$(openssl rand -hex 16)

cat >/etc/custom-panel/admin-credentials.txt <<EOF
Username: admin
Password: $PASS
EOF

chmod 600 /etc/custom-panel/admin-credentials.txt

cp -r panel agent database $BASE/

cat >/etc/systemd/system/custom-panel.service <<EOF
[Unit]
Description=Custom Panel

[Service]
WorkingDirectory=$BASE
ExecStart=$BASE/venv/bin/python3 $BASE/panel/app.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/custom-panel-agent.service <<EOF
[Unit]
Description=Custom Panel Agent

[Service]
WorkingDirectory=$BASE
ExecStart=$BASE/venv/bin/python3 $BASE/agent/main.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable custom-panel custom-panel-agent
systemctl restart custom-panel custom-panel-agent

echo "Installed"
cat /etc/custom-panel/admin-credentials.txt
