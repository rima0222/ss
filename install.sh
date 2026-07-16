#!/usr/bin/env bash
set -Eeuo pipefail

APP=/etc/custom-panel
REPO="${CUSTOM_PANEL_REPO_URL:-https://github.com/rima0222/ss.git}"
CLEAN="${CUSTOM_PANEL_CLEAN_INSTALL:-1}"

[[ "$EUID" -eq 0 ]] || { echo "Run as root."; exit 1; }

backup_old(){
  [[ -d "$APP" ]] || return 0
  local stamp rescue
  stamp="$(date -u +%Y%m%d-%H%M%S)"
  rescue="/root/custom-panel-rescue-$stamp"
  mkdir -p "$rescue"
  for item in data backups .env admin-credentials.txt; do
    [[ -e "$APP/$item" ]] && cp -a "$APP/$item" "$rescue/"
  done
  tar -C /root -czf "$rescue.tar.gz" "$(basename "$rescue")" 2>/dev/null || true
}

if [[ "$CLEAN" == "1" ]]; then
  systemctl disable --now custom-panel custom-panel-proxy custom-panel-accounting custom-panel-day-timer.timer 2>/dev/null || true
  backup_old
  rm -f /etc/systemd/system/custom-panel.service
  rm -f /etc/systemd/system/custom-panel-proxy.service
  rm -f /etc/systemd/system/custom-panel-accounting.service
  rm -f /etc/systemd/system/custom-panel-day.service
  rm -f /etc/systemd/system/custom-panel-day.timer
  rm -rf "$APP"
  systemctl daemon-reload
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv git curl ca-certificates openssh-server sqlite3 ufw

getent group panelusers >/dev/null || groupadd --system panelusers

cat > /usr/local/bin/panel-hold <<'EOF'
#!/usr/bin/env bash
trap 'exit 0' TERM INT HUP
while true; do sleep 3600; done
EOF
chmod 755 /usr/local/bin/panel-hold
grep -qxF '/usr/local/bin/panel-hold' /etc/shells || echo '/usr/local/bin/panel-hold' >> /etc/shells

cat > /etc/ssh/sshd_config.d/99-custom-panel.conf <<'EOF'
Port 22
Port 2222
ListenAddress 0.0.0.0
PasswordAuthentication yes
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password

Match Group panelusers
    ForceCommand /usr/local/bin/panel-hold
    PermitTTY no
    X11Forwarding no
    AllowAgentForwarding no
    AllowTcpForwarding yes
    GatewayPorts no
EOF
sshd -t
systemctl enable --now ssh
systemctl restart ssh

rm -rf "$APP"
git clone --depth=1 "$REPO" "$APP"
python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install --upgrade pip
"$APP/venv/bin/pip" install -r "$APP/requirements.txt"

mkdir -p "$APP/data" "$APP/backups" "$APP/runtime"
chmod 750 "$APP" "$APP/data" "$APP/backups" "$APP/runtime"

SERVER_HOST="${CUSTOM_PANEL_SERVER_HOST:-$(curl -4fsS --max-time 10 https://api.ipify.org || hostname -I | awk '{print $1}')}"
[[ -n "$SERVER_HOST" ]] || { echo "Could not detect server IP."; exit 1; }

ADMIN_PASSWORD="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(18))
PY
)"
SECRET="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"

cat > "$APP/.env" <<EOF
CUSTOM_PANEL_SECRET_KEY=$SECRET
CUSTOM_PANEL_ADMIN_USERNAME=admin
CUSTOM_PANEL_ADMIN_PASSWORD=$ADMIN_PASSWORD
CUSTOM_PANEL_DB=$APP/data/panel.db
CUSTOM_PANEL_SERVER_HOST=$SERVER_HOST
CUSTOM_PANEL_INTERNAL_SSH_PORT=2222
CUSTOM_PANEL_PORT_START=20000
CUSTOM_PANEL_PORT_END=29999
EOF
cat > "$APP/admin-credentials.txt" <<EOF
Username: admin
Password: $ADMIN_PASSWORD
EOF
chmod 600 "$APP/.env" "$APP/admin-credentials.txt"

cat > /etc/systemd/system/custom-panel-proxy.service <<EOF
[Unit]
Description=Custom Panel async SSH traffic proxy
After=network-online.target ssh.service
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$APP
EnvironmentFile=$APP/.env
ExecStart=$APP/venv/bin/python -m app.proxy_runtime
Restart=always
RestartSec=2
LimitNOFILE=65535
Nice=5

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/custom-panel-accounting.service <<EOF
[Unit]
Description=Custom Panel quota enforcement
After=custom-panel-proxy.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$APP
EnvironmentFile=$APP/.env
ExecStart=$APP/venv/bin/python -m app.accounting_worker
Restart=always
RestartSec=3
ProtectSystem=full
ReadWritePaths=$APP/data /run
NoNewPrivileges=true
Nice=10

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/custom-panel.service <<EOF
[Unit]
Description=Custom Panel
After=network-online.target custom-panel-proxy.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$APP
EnvironmentFile=$APP/.env
ExecStart=$APP/venv/bin/gunicorn --workers 1 --threads 4 --timeout 30 --keep-alive 3 --bind 0.0.0.0:5000 "app:create_app()"
Restart=always
RestartSec=3
ProtectSystem=no
ProtectHome=no
NoNewPrivileges=false
ReadWritePaths=$APP/data $APP/backups $APP/runtime /etc /run
LimitNOFILE=65535
Nice=5

[Install]
WantedBy=multi-user.target
EOF

ufw allow OpenSSH >/dev/null 2>&1 || true
ufw allow 5000/tcp >/dev/null 2>&1 || true
ufw allow 20000:29999/tcp >/dev/null 2>&1 || true
ufw --force enable >/dev/null 2>&1 || true

systemctl daemon-reload
systemctl enable custom-panel-proxy custom-panel-accounting custom-panel >/dev/null
systemctl restart custom-panel-proxy custom-panel-accounting custom-panel
sleep 2

for service in ssh custom-panel-proxy custom-panel-accounting custom-panel; do
  if ! systemctl is-active --quiet "$service"; then
    journalctl -u "$service" -n 100 --no-pager || true
    echo "Service failed: $service"
    exit 1
  fi
done
curl -fsS --max-time 10 http://127.0.0.1:5000/login >/dev/null

echo "Installed: http://$SERVER_HOST:5000"
echo "Credentials: $APP/admin-credentials.txt"
echo "Show credentials: sudo bash $APP/show-credentials.sh"
