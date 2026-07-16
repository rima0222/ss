#!/usr/bin/env bash
set -Eeuo pipefail

APP=/etc/custom-panel
REPO="${CUSTOM_PANEL_REPO_URL:-https://github.com/rima0222/ss.git}"
CLEAN="${CUSTOM_PANEL_CLEAN_INSTALL:-1}"

[[ "$EUID" -eq 0 ]] || { echo "Run as root."; exit 1; }

backup_old(){
  [[ -d "$APP" ]] || return 0
  stamp="$(date -u +%Y%m%d-%H%M%S)"
  rescue="/root/custom-panel-rescue-$stamp"
  mkdir -p "$rescue"
  cp -a "$APP/data" "$rescue/" 2>/dev/null || true
  cp -a "$APP/backups" "$rescue/" 2>/dev/null || true
  cp -a "$APP/.env" "$rescue/" 2>/dev/null || true
  cp -a "$APP/admin-credentials.txt" "$rescue/" 2>/dev/null || true
  tar -C /root -czf "$rescue.tar.gz" "$(basename "$rescue")" 2>/dev/null || true
}

if [[ "$CLEAN" == "1" ]]; then
  systemctl disable --now custom-panel custom-panel-proxy custom-panel-accounting 2>/dev/null || true
  systemctl disable --now dropbear 2>/dev/null || true
  backup_old
  rm -f /etc/systemd/system/custom-panel.service
  rm -f /etc/systemd/system/custom-panel-proxy.service
  rm -f /etc/systemd/system/custom-panel-accounting.service
  rm -rf "$APP"
  systemctl daemon-reload
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y \
  python3 python3-venv git curl ca-certificates \
  openssh-server dropbear sqlite3 ufw openssl

systemctl enable --now ssh
getent group panelusers >/dev/null || groupadd --system panelusers

cat > /usr/local/bin/panel-hold <<'EOF'
#!/usr/bin/env bash
trap 'exit 0' TERM INT HUP
while true; do sleep 3600; done
EOF
chmod 755 /usr/local/bin/panel-hold

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
systemctl restart ssh

mkdir -p /etc/default
cat > /etc/default/dropbear <<'EOF'
NO_START=0
DROPBEAR_PORT=2223
DROPBEAR_EXTRA_ARGS="-w -s"
DROPBEAR_BANNER=""
EOF
systemctl enable --now dropbear

rm -rf "$APP"
git clone --depth=1 "$REPO" "$APP"
python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install --upgrade pip
"$APP/venv/bin/pip" install -r "$APP/requirements.txt"

mkdir -p "$APP/data" "$APP/backups" "$APP/runtime" "$APP/tls"
chmod 750 "$APP" "$APP/data" "$APP/backups" "$APP/runtime"

SERVER_HOST="${CUSTOM_PANEL_SERVER_HOST:-$(curl -4fsS --max-time 10 https://api.ipify.org || hostname -I | awk '{print $1}')}"
[[ -n "$SERVER_HOST" ]] || { echo "Could not detect IP."; exit 1; }

openssl req -x509 -newkey rsa:3072 -nodes -days 1825 \
  -keyout "$APP/tls/server.key" \
  -out "$APP/tls/server.crt" \
  -subj "/CN=$SERVER_HOST" \
  -addext "subjectAltName=IP:$SERVER_HOST"
chmod 600 "$APP/tls/server.key"

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
CUSTOM_PANEL_TLS_CERT=$APP/tls/server.crt
CUSTOM_PANEL_TLS_KEY=$APP/tls/server.key
EOF

cat > "$APP/admin-credentials.txt" <<EOF
Username: admin
Password: $ADMIN_PASSWORD
EOF
chmod 600 "$APP/.env" "$APP/admin-credentials.txt"

cat > /etc/systemd/system/custom-panel-proxy.service <<EOF
[Unit]
Description=Custom Panel per-user SSH proxies
After=network-online.target ssh.service dropbear.service
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

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/custom-panel-accounting.service <<EOF
[Unit]
Description=Custom Panel accounting
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
ExecStart=$APP/venv/bin/gunicorn --workers 2 --threads 4 --timeout 30 --bind 0.0.0.0:5000 "app:create_app()"
Restart=always
RestartSec=3
ProtectSystem=no
NoNewPrivileges=false
ReadWritePaths=$APP/data $APP/backups $APP/runtime /etc/passwd /etc/shadow /etc/group /run
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

ufw allow OpenSSH >/dev/null 2>&1 || true
ufw allow 5000/tcp >/dev/null 2>&1 || true
ufw allow 20000:39999/tcp >/dev/null 2>&1 || true
ufw --force enable >/dev/null 2>&1 || true

systemctl daemon-reload
systemctl enable custom-panel-proxy custom-panel-accounting custom-panel >/dev/null
systemctl restart custom-panel-proxy custom-panel-accounting custom-panel
sleep 2

systemctl is-active --quiet ssh || exit 1
systemctl is-active --quiet dropbear || exit 1
systemctl is-active --quiet custom-panel-proxy || { journalctl -u custom-panel-proxy -n 100 --no-pager; exit 1; }
systemctl is-active --quiet custom-panel-accounting || exit 1
systemctl is-active --quiet custom-panel || exit 1
curl -fsS --max-time 10 http://127.0.0.1:5000/login >/dev/null

echo "Installed: http://$SERVER_HOST:5000"
echo "Credentials: $APP/admin-credentials.txt"
echo "Show credentials: sudo bash $APP/show-credentials.sh"
