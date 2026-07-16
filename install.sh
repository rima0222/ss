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
  systemctl disable --now custom-panel custom-panel-proxy custom-panel-accounting custom-panel-helper 2>/dev/null || true
  backup_old
  rm -f /etc/systemd/system/custom-panel.service
  rm -f /etc/systemd/system/custom-panel-proxy.service
  rm -f /etc/systemd/system/custom-panel-accounting.service
  rm -f /etc/systemd/system/custom-panel-helper.service
  rm -rf "$APP"
  systemctl daemon-reload
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv git curl ca-certificates openssh-server sqlite3 ufw

getent group panelusers >/dev/null || groupadd --system panelusers
getent group custompanel >/dev/null || groupadd --system custompanel
id -u custompanel >/dev/null 2>&1 || useradd --system --no-create-home --gid custompanel --shell /usr/sbin/nologin custompanel
id -u panelproxy >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin panelproxy
usermod -g custompanel custompanel
usermod -g custompanel panelproxy

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

mkdir -p "$APP/data" "$APP/backups" "$APP/runtime" /run/custom-panel

# Application code is root-owned but readable/traversable by custompanel group.
chown -R root:custompanel "$APP"
find "$APP" -type d -exec chmod 750 {} +
find "$APP" -type f -exec chmod 640 {} +
find "$APP/venv/bin" -type f -exec chmod 750 {} +
chmod 750 "$APP/install.sh" "$APP/show-credentials.sh" "$APP/reset-admin-password.sh" 2>/dev/null || true

# Only runtime data is writable by panel services.
chown -R custompanel:custompanel "$APP/data" "$APP/backups" "$APP/runtime"
chmod 770 "$APP/data" "$APP/backups" "$APP/runtime"

chown root:custompanel /run/custom-panel
chmod 770 /run/custom-panel

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
DATA_KEY="$("$APP/venv/bin/python" - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
)"
ADMIN_HASH="$("$APP/venv/bin/python" - <<PY
from werkzeug.security import generate_password_hash
print(generate_password_hash("""$ADMIN_PASSWORD"""))
PY
)"

cat > "$APP/.env" <<EOF
CUSTOM_PANEL_SECRET_KEY=$SECRET
CUSTOM_PANEL_ADMIN_USERNAME=admin
CUSTOM_PANEL_ADMIN_PASSWORD_HASH=$ADMIN_HASH
CUSTOM_PANEL_DATA_KEY=$DATA_KEY
CUSTOM_PANEL_DB=$APP/data/panel.db
CUSTOM_PANEL_SERVER_HOST=$SERVER_HOST
CUSTOM_PANEL_INTERNAL_SSH_PORT=2222
CUSTOM_PANEL_PORT_START=20000
CUSTOM_PANEL_PORT_END=29999
CUSTOM_PANEL_HELPER_SOCKET=/run/custom-panel/helper.sock
EOF
cat > "$APP/admin-credentials.txt" <<EOF
Username: admin
Password: $ADMIN_PASSWORD
EOF
chown root:custompanel "$APP/.env"
chmod 640 "$APP/.env"
chmod 600 "$APP/admin-credentials.txt"

cat > /etc/systemd/system/custom-panel-helper.service <<EOF
[Unit]
Description=Custom Panel privileged account helper
After=local-fs.target
Before=custom-panel.service custom-panel-accounting.service
StartLimitIntervalSec=60
StartLimitBurst=10

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$APP
EnvironmentFile=$APP/.env
ExecStart=$APP/venv/bin/python -m app.account_helper
Restart=on-failure
RestartSec=2
PrivateTmp=true
NoNewPrivileges=false
LimitNOFILE=1024

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/custom-panel-proxy.service <<EOF
[Unit]
Description=Custom Panel async OpenSSH proxy
After=network-online.target ssh.service
Wants=network-online.target
StartLimitIntervalSec=60
StartLimitBurst=10

[Service]
Type=simple
User=panelproxy
Group=custompanel
WorkingDirectory=$APP
EnvironmentFile=$APP/.env
ExecStart=$APP/venv/bin/python -m app.proxy_runtime
Restart=on-failure
RestartSec=2
PrivateTmp=true
NoNewPrivileges=true
LimitNOFILE=65535
Nice=5

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/custom-panel-accounting.service <<EOF
[Unit]
Description=Custom Panel accounting and quota enforcement
After=custom-panel-helper.service custom-panel-proxy.service
Requires=custom-panel-helper.service
StartLimitIntervalSec=60
StartLimitBurst=10

[Service]
Type=simple
User=custompanel
Group=custompanel
WorkingDirectory=$APP
EnvironmentFile=$APP/.env
ExecStart=$APP/venv/bin/python -m app.accounting_worker
Restart=on-failure
RestartSec=3
PrivateTmp=true
NoNewPrivileges=true
LimitNOFILE=2048
Nice=10

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/custom-panel.service <<EOF
[Unit]
Description=Custom Panel web application
After=network-online.target custom-panel-helper.service custom-panel-proxy.service
Requires=custom-panel-helper.service
StartLimitIntervalSec=60
StartLimitBurst=10

[Service]
Type=simple
User=custompanel
Group=custompanel
WorkingDirectory=$APP
EnvironmentFile=$APP/.env
ExecStart=$APP/venv/bin/gunicorn --workers 1 --threads 4 --timeout 30 --keep-alive 3 --max-requests 3000 --max-requests-jitter 300 --bind 0.0.0.0:5000 "app:create_app()"
Restart=on-failure
RestartSec=3
PrivateTmp=true
NoNewPrivileges=true
LimitNOFILE=8192
Nice=5

[Install]
WantedBy=multi-user.target
EOF

ufw allow OpenSSH >/dev/null 2>&1 || true
ufw allow 5000/tcp >/dev/null 2>&1 || true
ufw allow 20000:29999/tcp >/dev/null 2>&1 || true
ufw --force enable >/dev/null 2>&1 || true

# Permission and import preflight tests.
namei -l "$APP" || true
sudo -u panelproxy test -x "$APP"
sudo -u custompanel test -x "$APP"
sudo -u panelproxy test -r "$APP/app/proxy_runtime.py"
sudo -u custompanel test -r "$APP/app/__init__.py"
sudo -u panelproxy test -w "$APP/data"
sudo -u custompanel test -w "$APP/data"

sudo -u panelproxy env $(cat "$APP/.env" | xargs) \
  "$APP/venv/bin/python" -c "from app.db import init_db; init_db('$APP/data/panel.db')"
sudo -u custompanel env $(cat "$APP/.env" | xargs) \
  "$APP/venv/bin/python" -c "from app import create_app; create_app()"

cat > /etc/tmpfiles.d/custom-panel.conf <<'EOF'
d /run/custom-panel 0770 root custompanel -
EOF
systemd-tmpfiles --create /etc/tmpfiles.d/custom-panel.conf

systemctl daemon-reload
systemctl reset-failed custom-panel-helper custom-panel-proxy custom-panel-accounting custom-panel 2>/dev/null || true
systemctl enable custom-panel-helper custom-panel-proxy custom-panel-accounting custom-panel >/dev/null
systemctl stop custom-panel-helper custom-panel-proxy custom-panel-accounting custom-panel 2>/dev/null || true
systemctl start custom-panel-helper
sleep 1
systemctl start custom-panel-proxy
systemctl start custom-panel-accounting
systemctl start custom-panel
sleep 3

for service in ssh custom-panel-helper custom-panel-proxy custom-panel-accounting custom-panel; do
  if ! systemctl is-active --quiet "$service"; then
    journalctl -u "$service" -n 120 --no-pager || true
    echo "Service failed: $service"
    exit 1
  fi
done
curl -fsS --max-time 10 http://127.0.0.1:5000/login >/dev/null

echo "Installed: http://$SERVER_HOST:5000"
echo "Credentials: $APP/admin-credentials.txt"
echo "Show credentials: sudo bash $APP/show-credentials.sh"
