#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="${CUSTOM_PANEL_REPO_URL:-https://github.com/rima0222/ss.git}"
APP=/opt/custom-panel
STATE=/var/lib/custom-panel
CONF=/etc/custom-panel
RUNTIME=/run/custom-panel
PANEL_PORT="${CUSTOM_PANEL_PANEL_PORT:-5000}"
WS_PORT="${CUSTOM_PANEL_WS_PORT:-8080}"

[[ $EUID -eq 0 ]] || { echo "Run as root"; exit 1; }

echo "[*] Clean removal of previous panel state"
for service in custom-panel custom-panel-agent custom-panel-web custom-panel-gateway custom-panel-manager custom-panel-helper custom-panel-proxy custom-panel-accounting custom-panel-sshd; do
  systemctl disable --now "$service" 2>/dev/null || true
  rm -f "/etc/systemd/system/$service.service"
done

managed_users="$(
  {
    getent group cpusers | awk -F: '{gsub(/,/, "\n", $4); print $4}'
    getent group panelusers | awk -F: '{gsub(/,/, "\n", $4); print $4}'
    getent passwd | awk -F: '$5=="custom-panel-managed"{print $1}'
  } | sed '/^$/d' | sort -u
)"
while read -r user; do
  [[ -z "$user" ]] && continue
  pkill -KILL -u "$user" 2>/dev/null || true
  userdel -r "$user" 2>/dev/null || true
done <<< "$managed_users"

rm -rf "$APP" "$STATE" "$CONF" "$RUNTIME"
rm -f /etc/ssh/sshd_config.d/98-custom-panel-deny.conf
rm -f /etc/ssh/sshd_config_custom_panel
rm -f /etc/pam.d/custom-panel-sshd
rm -f /etc/tmpfiles.d/custom-panel.conf
groupdel cpusers 2>/dev/null || true
groupdel panelusers 2>/dev/null || true
userdel custompanel 2>/dev/null || true
groupdel custompanel 2>/dev/null || true
systemctl daemon-reload

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv git curl ca-certificates openssh-server sqlite3 ufw util-linux

getent group custompanel >/dev/null || groupadd --system custompanel
id custompanel >/dev/null 2>&1 || useradd --system --no-create-home --gid custompanel --shell /usr/sbin/nologin custompanel
getent group cpusers >/dev/null || groupadd --system cpusers

mkdir -p "$APP" "$STATE" "$CONF" "$RUNTIME"
git clone --depth=1 "$REPO_URL" "$APP"
test -f "$APP/requirements.txt"
test -f "$APP/custom_panel/managerd.py"

python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install --upgrade pip
"$APP/venv/bin/pip" install -r "$APP/requirements.txt"

mkdir -p /usr/local/lib/custom-panel
cat > /usr/local/lib/custom-panel/panel-hold <<'EOF'
#!/usr/bin/env bash
trap 'exit 0' TERM INT HUP
while true; do sleep 3600; done
EOF
chmod 755 /usr/local/lib/custom-panel/panel-hold
grep -qxF /usr/local/lib/custom-panel/panel-hold /etc/shells || echo /usr/local/lib/custom-panel/panel-hold >> /etc/shells

SERVER_HOST="${CUSTOM_PANEL_SERVER_HOST:-$(curl -4fsS --max-time 10 https://api.ipify.org || hostname -I | awk '{print $1}')}"
ADMIN_PASSWORD="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(20))
PY
)"
SECRET_KEY="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"
DATA_KEY="$("$APP/venv/bin/python" - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
)"

cat > "$CONF/panel.env" <<EOF
CP_DB_PATH=$STATE/panel.db
CP_MANAGER_SOCKET=$RUNTIME/manager.sock
CP_HELPER_SOCKET=$RUNTIME/helper.sock
CP_SECRET_KEY=$SECRET_KEY
CP_DATA_KEY=$DATA_KEY
CP_SERVER_HOST=$SERVER_HOST
CP_PANEL_PORT=$PANEL_PORT
CP_WS_PORT=$WS_PORT
CP_TCP_PORT_START=20000
CP_TCP_PORT_END=24999
CP_BACKEND_PORT_START=30000
CP_BACKEND_PORT_END=34999
EOF
chown root:custompanel "$CONF/panel.env"
chmod 640 "$CONF/panel.env"

cat > "$CONF/admin-credentials.txt" <<EOF
Username: admin
Password: $ADMIN_PASSWORD
EOF
chmod 600 "$CONF/admin-credentials.txt"

chown -R root:custompanel "$APP"
find "$APP" -type d -exec chmod 750 {} +
find "$APP" -type f -exec chmod 640 {} +
find "$APP/venv/bin" -type f -exec chmod 750 {} +
chmod 750 "$APP"/*.sh
chown -R custompanel:custompanel "$STATE" "$RUNTIME"
chmod 770 "$STATE" "$RUNTIME"

cat > /etc/tmpfiles.d/custom-panel.conf <<EOF
d $RUNTIME 0770 custompanel custompanel -
d $RUNTIME/pam-spool 0770 custompanel custompanel -
EOF
systemd-tmpfiles --create /etc/tmpfiles.d/custom-panel.conf

cat > /etc/ssh/sshd_config.d/98-custom-panel-deny.conf <<'EOF'
DenyGroups cpusers
EOF
/usr/sbin/sshd -t
systemctl enable --now ssh
systemctl restart ssh

cat > /etc/pam.d/custom-panel-sshd <<EOF
@include common-auth
@include common-account
@include common-session
session optional pam_exec.so quiet $APP/venv/bin/python $APP/custom_panel/pam_event.py
@include common-password
EOF

cat > /etc/ssh/sshd_config_custom_panel <<'EOF'
ListenAddress 127.0.0.1:2299
Protocol 2
HostKey /etc/ssh/ssh_host_ed25519_key
HostKey /etc/ssh/ssh_host_rsa_key
UsePAM yes
PAMServiceName custom-panel-sshd
PasswordAuthentication yes
KbdInteractiveAuthentication no
PubkeyAuthentication no
PermitRootLogin no
PermitEmptyPasswords no
AllowGroups cpusers
AllowUsers __cp_disabled__
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding yes
GatewayPorts no
PermitTunnel no
PermitTTY no
PrintMotd no
UseDNS no
ClientAliveInterval 45
ClientAliveCountMax 2
MaxAuthTries 4
LoginGraceTime 30
PidFile /run/custom-panel-sshd.pid
ForceCommand /usr/local/lib/custom-panel/panel-hold
EOF
/usr/sbin/sshd -t -f /etc/ssh/sshd_config_custom_panel

cat > /etc/systemd/system/custom-panel-sshd.service <<EOF
[Unit]
Description=Custom Panel internal OpenSSH
After=network.target
Before=custom-panel-gateway.service

[Service]
Type=notify
ExecStart=/usr/sbin/sshd -D -f /etc/ssh/sshd_config_custom_panel
ExecReload=/bin/kill -HUP \$MAINPID
KillMode=process
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/custom-panel-helper.service <<EOF
[Unit]
Description=Custom Panel privileged helper
After=local-fs.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$APP
EnvironmentFile=$CONF/panel.env
Environment=PYTHONPATH=$APP
ExecStart=$APP/venv/bin/python -m custom_panel.helperd
Restart=always
RestartSec=2
PrivateTmp=true
LimitNOFILE=2048

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/custom-panel-manager.service <<EOF
[Unit]
Description=Custom Panel management engine
After=custom-panel-helper.service custom-panel-sshd.service
Requires=custom-panel-helper.service custom-panel-sshd.service

[Service]
Type=simple
User=custompanel
Group=custompanel
WorkingDirectory=$APP
EnvironmentFile=$CONF/panel.env
Environment=PYTHONPATH=$APP
ExecStart=$APP/venv/bin/python -m custom_panel.managerd
Restart=always
RestartSec=2
PrivateTmp=true
NoNewPrivileges=true
UMask=0007
LimitNOFILE=8192

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/custom-panel-gateway.service <<EOF
[Unit]
Description=Custom Panel OpenSSH and WebSocket gateway
After=custom-panel-manager.service
Requires=custom-panel-manager.service

[Service]
Type=simple
User=custompanel
Group=custompanel
WorkingDirectory=$APP
EnvironmentFile=$CONF/panel.env
Environment=PYTHONPATH=$APP
ExecStart=$APP/venv/bin/python -m custom_panel.gatewayd
Restart=always
RestartSec=2
PrivateTmp=true
NoNewPrivileges=true
UMask=0007
LimitNOFILE=65535
Nice=-2

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/custom-panel-web.service <<EOF
[Unit]
Description=Custom Panel web interface
After=custom-panel-manager.service
Requires=custom-panel-manager.service

[Service]
Type=simple
User=custompanel
Group=custompanel
WorkingDirectory=$APP
EnvironmentFile=$CONF/panel.env
Environment=PYTHONPATH=$APP
ExecStart=$APP/venv/bin/gunicorn --workers 1 --threads 4 --timeout 30 --keep-alive 3 --max-requests 4000 --max-requests-jitter 300 --bind 0.0.0.0:$PANEL_PORT "custom_panel.web:create_app()"
Restart=always
RestartSec=2
PrivateTmp=true
NoNewPrivileges=true
UMask=0007
LimitNOFILE=8192

[Install]
WantedBy=multi-user.target
EOF

set -a
. "$CONF/panel.env"
set +a
runuser -u custompanel -- env PYTHONPATH="$APP" \
  "$APP/venv/bin/python" -m custom_panel.cli init \
  --admin-user admin --admin-password "$ADMIN_PASSWORD"

ufw allow OpenSSH >/dev/null 2>&1 || true
ufw allow "$PANEL_PORT/tcp" >/dev/null 2>&1 || true
ufw allow "$WS_PORT/tcp" >/dev/null 2>&1 || true
ufw allow 20000:24999/tcp >/dev/null 2>&1 || true
ufw --force enable >/dev/null 2>&1 || true

systemctl daemon-reload
systemctl enable custom-panel-sshd custom-panel-helper custom-panel-manager custom-panel-gateway custom-panel-web >/dev/null
systemctl start custom-panel-sshd
systemctl start custom-panel-helper
sleep 1
systemctl start custom-panel-manager
sleep 2
systemctl start custom-panel-gateway
systemctl start custom-panel-web
sleep 4

for service in custom-panel-sshd custom-panel-helper custom-panel-manager custom-panel-gateway custom-panel-web; do
  if ! systemctl is-active --quiet "$service"; then
    journalctl -u "$service" -n 150 --no-pager || true
    echo "Installation failed: $service is not active"
    exit 1
  fi
done

curl -fsS --max-time 10 "http://127.0.0.1:$PANEL_PORT/api/health" >/dev/null
runuser -u custompanel -- env PYTHONPATH="$APP" \
  "$APP/venv/bin/python" -m custom_panel.cli health >/dev/null

echo
echo "=============================================="
echo " Custom Panel installed successfully"
echo " Panel: http://$SERVER_HOST:$PANEL_PORT"
cat "$CONF/admin-credentials.txt"
echo " Show credentials: sudo bash $APP/show-credentials.sh"
echo " Diagnostics: sudo bash $APP/diagnose.sh"
echo "=============================================="
