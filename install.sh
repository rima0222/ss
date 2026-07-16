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

if ! pgrep -x useradd >/dev/null 2>&1 &&
   ! pgrep -x usermod >/dev/null 2>&1 &&
   ! pgrep -x userdel >/dev/null 2>&1 &&
   ! pgrep -x chpasswd >/dev/null 2>&1; then
  rm -f /etc/passwd.lock /etc/shadow.lock /etc/group.lock /etc/gshadow.lock
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv git curl ca-certificates openssh-server sqlite3 ufw util-linux

getent group panelusers >/dev/null || groupadd --system panelusers
getent group custompanel >/dev/null || groupadd --system custompanel
id -u custompanel >/dev/null 2>&1 || useradd --system --no-create-home --gid custompanel --shell /usr/sbin/nologin custompanel
usermod -g custompanel custompanel

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

git clone --depth=1 "$REPO" "$APP"
test -f "$APP/app/__init__.py"
test -f "$APP/requirements.txt"
test -f "$APP/templates/index.html"

python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install --upgrade pip
"$APP/venv/bin/pip" install -r "$APP/requirements.txt"

mkdir -p "$APP/data" "$APP/backups" "$APP/runtime" /run/custom-panel
chown -R root:custompanel "$APP"
find "$APP" -type d -exec chmod 750 {} +
find "$APP" -type f -exec chmod 640 {} +
find "$APP/venv/bin" -type f -exec chmod 750 {} +
chmod 750 "$APP/install.sh" "$APP/show-credentials.sh" "$APP/reset-admin-password.sh" "$APP/diagnose.sh"
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
CUSTOM_PANEL_TCP_PORT_START=20000
CUSTOM_PANEL_TCP_PORT_END=24999
CUSTOM_PANEL_WS_PORT_START=25000
CUSTOM_PANEL_WS_PORT_END=29999
CUSTOM_PANEL_HELPER_SOCKET=/run/custom-panel/helper.sock
EOF
cat > "$APP/admin-credentials.txt" <<EOF
Username: admin
Password: $ADMIN_PASSWORD
EOF
chown root:custompanel "$APP/.env"
chmod 640 "$APP/.env"
chmod 600 "$APP/admin-credentials.txt"

cat > /etc/tmpfiles.d/custom-panel.conf <<'EOF'
d /run/custom-panel 0770 root custompanel -
EOF
systemd-tmpfiles --create /etc/tmpfiles.d/custom-panel.conf

cat > /etc/systemd/system/custom-panel-helper.service <<EOF
[Unit]
Description=Custom Panel account helper
After=local-fs.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$APP
EnvironmentFile=$APP/.env
Environment=PYTHONPATH=$APP
ExecStart=$APP/venv/bin/python -m app.account_helper
Restart=on-failure
RestartSec=2
PrivateTmp=true
LimitNOFILE=1024

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/custom-panel-proxy.service <<EOF
[Unit]
Description=OpenSSH and SSH WebSocket proxy
After=network-online.target ssh.service
Wants=network-online.target

[Service]
Type=simple
User=custompanel
Group=custompanel
WorkingDirectory=$APP
EnvironmentFile=$APP/.env
Environment=PYTHONPATH=$APP
ExecStart=$APP/venv/bin/python -m app.proxy_runtime
Restart=on-failure
RestartSec=2
PrivateTmp=true
NoNewPrivileges=true
UMask=0007
LimitNOFILE=65535
Nice=5

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/custom-panel-accounting.service <<EOF
[Unit]
Description=Custom Panel accounting
After=custom-panel-helper.service custom-panel-proxy.service
Requires=custom-panel-helper.service

[Service]
Type=simple
User=custompanel
Group=custompanel
WorkingDirectory=$APP
EnvironmentFile=$APP/.env
Environment=PYTHONPATH=$APP
ExecStart=$APP/venv/bin/python -m app.accounting_worker
Restart=on-failure
RestartSec=3
PrivateTmp=true
NoNewPrivileges=true
UMask=0007
Nice=10

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/custom-panel.service <<EOF
[Unit]
Description=Custom Panel web
After=network-online.target custom-panel-helper.service custom-panel-proxy.service
Requires=custom-panel-helper.service

[Service]
Type=simple
User=custompanel
Group=custompanel
WorkingDirectory=$APP
EnvironmentFile=$APP/.env
Environment=PYTHONPATH=$APP
ExecStart=$APP/venv/bin/gunicorn --workers 1 --threads 4 --timeout 30 --keep-alive 3 --max-requests 3000 --max-requests-jitter 300 --bind 0.0.0.0:5000 "app:create_app()"
Restart=on-failure
RestartSec=3
PrivateTmp=true
NoNewPrivileges=true
UMask=0007
LimitNOFILE=8192
Nice=5

[Install]
WantedBy=multi-user.target
EOF

runuser -u custompanel -- test -x "$APP"
runuser -u custompanel -- test -r "$APP/app/proxy_runtime.py"
runuser -u custompanel -- test -r "$APP/app/__init__.py"
runuser -u custompanel -- test -w "$APP/data"

# Create and verify the SQLite database using the same user that runs all
# database-writing services. This prevents readonly database errors.
runuser -u custompanel -- env \
  PYTHONPATH="$APP" \
  CUSTOM_PANEL_SECRET_KEY="$SECRET" \
  CUSTOM_PANEL_ADMIN_USERNAME="admin" \
  CUSTOM_PANEL_ADMIN_PASSWORD_HASH="$ADMIN_HASH" \
  CUSTOM_PANEL_DATA_KEY="$DATA_KEY" \
  CUSTOM_PANEL_DB="$APP/data/panel.db" \
  CUSTOM_PANEL_SERVER_HOST="$SERVER_HOST" \
  CUSTOM_PANEL_INTERNAL_SSH_PORT="2222" \
  CUSTOM_PANEL_TCP_PORT_START="20000" \
  CUSTOM_PANEL_TCP_PORT_END="24999" \
  CUSTOM_PANEL_WS_PORT_START="25000" \
  CUSTOM_PANEL_WS_PORT_END="29999" \
  CUSTOM_PANEL_HELPER_SOCKET="/run/custom-panel/helper.sock" \
  "$APP/venv/bin/python" - <<'PY'
from app.db import init_db, connect
from app.config import Config
init_db(Config.DB_PATH)
with connect() as conn:
    conn.execute("CREATE TABLE IF NOT EXISTS install_write_test(id INTEGER PRIMARY KEY, value TEXT)")
    conn.execute("INSERT OR REPLACE INTO install_write_test(id,value) VALUES(1,'ok')")
    conn.commit()
    assert conn.execute("SELECT value FROM install_write_test WHERE id=1").fetchone()[0] == "ok"
    conn.execute("DROP TABLE install_write_test")
    conn.commit()
print("SQLite write test: OK")
PY

chown -R custompanel:custompanel "$APP/data"
find "$APP/data" -type d -exec chmod 770 {} +
find "$APP/data" -type f -exec chmod 660 {} +

ufw allow OpenSSH >/dev/null 2>&1 || true
ufw allow 5000/tcp >/dev/null 2>&1 || true
ufw allow 20000:29999/tcp >/dev/null 2>&1 || true
ufw --force enable >/dev/null 2>&1 || true

systemctl daemon-reload
systemctl reset-failed custom-panel-helper custom-panel-proxy custom-panel-accounting custom-panel 2>/dev/null || true
systemctl enable custom-panel-helper custom-panel-proxy custom-panel-accounting custom-panel >/dev/null

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
runuser -u custompanel -- env PYTHONPATH="$APP" \
  CUSTOM_PANEL_SECRET_KEY="$SECRET" \
  CUSTOM_PANEL_ADMIN_USERNAME="admin" \
  CUSTOM_PANEL_ADMIN_PASSWORD_HASH="$ADMIN_HASH" \
  CUSTOM_PANEL_DATA_KEY="$DATA_KEY" \
  CUSTOM_PANEL_DB="$APP/data/panel.db" \
  CUSTOM_PANEL_SERVER_HOST="$SERVER_HOST" \
  CUSTOM_PANEL_INTERNAL_SSH_PORT="2222" \
  CUSTOM_PANEL_TCP_PORT_START="20000" \
  CUSTOM_PANEL_TCP_PORT_END="24999" \
  CUSTOM_PANEL_WS_PORT_START="25000" \
  CUSTOM_PANEL_WS_PORT_END="29999" \
  CUSTOM_PANEL_HELPER_SOCKET="/run/custom-panel/helper.sock" \
  "$APP/venv/bin/python" -c "from app.db import init_db,connect; from app.config import Config; init_db(Config.DB_PATH); c=connect().__enter__(); c.execute('PRAGMA wal_checkpoint(PASSIVE)'); c.close()"
ss -lnt | grep -qE '[:.]5000[[:space:]]'

echo "Installed: http://$SERVER_HOST:5000"
echo "Credentials: $APP/admin-credentials.txt"
echo "Show credentials: sudo bash $APP/show-credentials.sh"
