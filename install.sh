#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/etc/custom-panel"
REPO_URL="${CUSTOM_PANEL_REPO_URL:-https://github.com/rima0222/ss.git}"
CLEAN="${CUSTOM_PANEL_CLEAN_INSTALL:-1}"

[[ "$EUID" -eq 0 ]] || { echo "Run as root."; exit 1; }

backup_old(){
  [[ -d "$APP_DIR" ]] || return 0
  local stamp rescue
  stamp="$(date -u +%Y%m%d-%H%M%S)"
  rescue="/root/custom-panel-rescue-$stamp"
  mkdir -p "$rescue"
  cp -a "$APP_DIR/data" "$rescue/" 2>/dev/null || true
  cp -a "$APP_DIR/backups" "$rescue/" 2>/dev/null || true
  cp -a "$APP_DIR/.env" "$rescue/" 2>/dev/null || true
  cp -a "$APP_DIR/admin-credentials.txt" "$rescue/" 2>/dev/null || true
  tar -C /root -czf "$rescue.tar.gz" "$(basename "$rescue")" 2>/dev/null || true
}

if [[ "$CLEAN" == "1" ]]; then
  systemctl disable --now custom-panel.service custom-panel-accounting.service 2>/dev/null || true
  backup_old
  rm -f /etc/systemd/system/custom-panel.service
  rm -f /etc/systemd/system/custom-panel-accounting.service
  rm -rf "$APP_DIR"
  systemctl daemon-reload
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv git curl ca-certificates openssh-server sqlite3 ufw

systemctl enable --now ssh

# Official Xray installation script.
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install

rm -rf "$APP_DIR"
git clone --depth=1 "$REPO_URL" "$APP_DIR"

python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

mkdir -p "$APP_DIR/data" "$APP_DIR/backups" "$APP_DIR/runtime" /var/log/xray
chmod 750 "$APP_DIR" "$APP_DIR/data" "$APP_DIR/backups" "$APP_DIR/runtime"
chown -R nobody:nogroup /var/log/xray 2>/dev/null || true

SERVER_HOST="${CUSTOM_PANEL_SERVER_HOST:-$(curl -4fsS --max-time 10 https://api.ipify.org || hostname -I | awk '{print $1}')}"
[[ -n "$SERVER_HOST" ]] || { echo "Could not detect server IP."; exit 1; }

ADMIN_PASSWORD="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(18))
PY
)"
SECRET_KEY="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"

cat > "$APP_DIR/.env" <<EOF
CUSTOM_PANEL_SECRET_KEY=$SECRET_KEY
CUSTOM_PANEL_ADMIN_USERNAME=admin
CUSTOM_PANEL_ADMIN_PASSWORD=$ADMIN_PASSWORD
CUSTOM_PANEL_DB=$APP_DIR/data/panel.db
CUSTOM_PANEL_SERVER_HOST=$SERVER_HOST
CUSTOM_PANEL_XRAY_PORT=8443
CUSTOM_PANEL_XRAY_API=127.0.0.1:10085
CUSTOM_PANEL_XRAY_CONFIG=/usr/local/etc/xray/config.json
EOF

cat > "$APP_DIR/admin-credentials.txt" <<EOF
Username: admin
Password: $ADMIN_PASSWORD
EOF
chmod 600 "$APP_DIR/.env" "$APP_DIR/admin-credentials.txt"

cat > /usr/local/etc/xray/config.json <<'EOF'
{
  "log": {
    "loglevel": "warning",
    "access": "/var/log/xray/access.log",
    "error": "/var/log/xray/error.log"
  },
  "api": {
    "tag": "api",
    "services": ["StatsService", "HandlerService"]
  },
  "stats": {},
  "policy": {
    "levels": {
      "0": {
        "statsUserUplink": true,
        "statsUserDownlink": true,
        "statsUserOnline": true
      }
    }
  },
  "inbounds": [
    {
      "tag": "api",
      "listen": "127.0.0.1",
      "port": 10085,
      "protocol": "tunnel",
      "settings": {"rewriteAddress": "127.0.0.1"}
    },
    {
      "tag": "vmess-in",
      "listen": "0.0.0.0",
      "port": 8443,
      "protocol": "vmess",
      "settings": {"clients": []},
      "streamSettings": {"network": "tcp", "security": "none"}
    }
  ],
  "outbounds": [
    {"tag": "direct", "protocol": "freedom"},
    {"tag": "block", "protocol": "blackhole"}
  ],
  "routing": {
    "rules": [
      {"type": "field", "inboundTag": ["api"], "outboundTag": "api"}
    ]
  }
}
EOF

/usr/local/bin/xray run -test -config /usr/local/etc/xray/config.json
systemctl enable --now xray

cat > /etc/systemd/system/custom-panel-accounting.service <<EOF
[Unit]
Description=Custom Panel accounting
After=network-online.target xray.service
Wants=network-online.target xray.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/python -m app.accounting_worker
Restart=on-failure
RestartSec=3
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=$APP_DIR/data $APP_DIR/runtime /run
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/custom-panel.service <<EOF
[Unit]
Description=Custom Panel
After=network-online.target xray.service
Wants=network-online.target xray.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/gunicorn --workers 2 --threads 4 --timeout 30 --bind 0.0.0.0:5000 "app:create_app()"
Restart=on-failure
RestartSec=3
PrivateTmp=true
ProtectSystem=no
NoNewPrivileges=false
ReadWritePaths=$APP_DIR/data $APP_DIR/backups $APP_DIR/runtime /usr/local/etc/xray /run
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

ufw allow OpenSSH >/dev/null 2>&1 || true
ufw allow 5000/tcp >/dev/null 2>&1 || true
ufw allow 8443/tcp >/dev/null 2>&1 || true
ufw --force enable >/dev/null 2>&1 || true

systemctl daemon-reload
systemctl enable custom-panel.service custom-panel-accounting.service >/dev/null
systemctl restart custom-panel.service custom-panel-accounting.service
sleep 2

systemctl is-active --quiet xray || { journalctl -u xray -n 100 --no-pager; exit 1; }
systemctl is-active --quiet custom-panel || { journalctl -u custom-panel -n 100 --no-pager; exit 1; }
systemctl is-active --quiet custom-panel-accounting || { journalctl -u custom-panel-accounting -n 100 --no-pager; exit 1; }
curl -fsS --max-time 10 http://127.0.0.1:5000/login >/dev/null

echo "Installed: http://$SERVER_HOST:5000"
echo "Credentials: $APP_DIR/admin-credentials.txt"
echo "Show credentials: sudo bash $APP_DIR/show-credentials.sh"
