#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/etc/custom-panel"
REPO_URL="${CUSTOM_PANEL_REPO_URL:-https://github.com/rima0222/ss.git}"
CLEAN_INSTALL="${CUSTOM_PANEL_CLEAN_INSTALL:-1}"

if [[ "$EUID" -ne 0 ]]; then
  echo "Run as root: sudo bash install.sh"
  exit 1
fi

log(){ printf '[*] %s\n' "$*"; }
die(){ printf '[!] %s\n' "$*" >&2; exit 1; }

backup_existing() {
  [[ -d "$APP_DIR" ]] || return 0
  local stamp rescue
  stamp="$(date -u +%Y%m%d-%H%M%S)"
  rescue="/root/custom-panel-rescue-$stamp"
  mkdir -p "$rescue"
  log "Saving emergency copy to $rescue"
  for item in data backups .env admin-credentials.txt; do
    [[ -e "$APP_DIR/$item" ]] && cp -a "$APP_DIR/$item" "$rescue/"
  done
  if [[ -f "$APP_DIR/data/panel.db" ]] && command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "$APP_DIR/data/panel.db" ".backup '$rescue/panel.db'" 2>/dev/null || true
  fi
  tar -C /root -czf "$rescue.tar.gz" "$(basename "$rescue")" 2>/dev/null || true
}

clean_install() {
  log "Stopping previous panel services"
  systemctl disable --now custom-panel.service 2>/dev/null || true
  systemctl disable --now custom-panel-accounting.service 2>/dev/null || true
  backup_existing
  rm -f /etc/systemd/system/custom-panel.service
  rm -f /etc/systemd/system/custom-panel-accounting.service
  rm -f /etc/systemd/system/custom-panel-wg-restore.service
  rm -rf "$APP_DIR"
  rm -f /etc/swanctl/conf.d/custom-panel.conf
  rm -f /etc/swanctl/conf.d/custom-panel-users.conf
  rm -f /etc/swanctl/custom-panel-users.json
  rm -f /etc/swanctl/x509/server.crt
  rm -f /etc/swanctl/x509ca/custom-panel-ca.crt
  rm -f /etc/swanctl/private/server.key
  rm -f /etc/swanctl/private/custom-panel-ca.key
  ufw --force delete allow 5000/tcp >/dev/null 2>&1 || true
  ufw --force delete allow 500/udp >/dev/null 2>&1 || true
  ufw --force delete allow 4500/udp >/dev/null 2>&1 || true
  systemctl daemon-reload
}

[[ "$CLEAN_INSTALL" == "1" ]] && clean_install

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y \
  python3 python3-venv git curl ca-certificates \
  openssh-server sqlite3 ufw \
  strongswan-swanctl strongswan-pki charon-systemd \
  libcharon-extra-plugins

systemctl enable --now ssh

git clone --depth=1 "$REPO_URL" "$APP_DIR"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

mkdir -p "$APP_DIR/data" "$APP_DIR/backups" "$APP_DIR/runtime"
chmod 750 "$APP_DIR" "$APP_DIR/data" "$APP_DIR/backups" "$APP_DIR/runtime"

SERVER_HOST="${CUSTOM_PANEL_SERVER_HOST:-$(curl -4fsS --max-time 10 https://api.ipify.org || hostname -I | awk '{print $1}')}"
[[ -n "$SERVER_HOST" ]] || die "Could not determine server IP."

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
CUSTOM_PANEL_IKE_REMOTE_ID=$SERVER_HOST
EOF

cat > "$APP_DIR/admin-credentials.txt" <<EOF
Username: admin
Password: $ADMIN_PASSWORD
EOF
chmod 600 "$APP_DIR/.env" "$APP_DIR/admin-credentials.txt"

cat > /etc/sysctl.d/99-custom-panel.conf <<'EOF'
net.ipv4.ip_forward=1
EOF
sysctl --system >/dev/null

SWAN="/etc/swanctl"
mkdir -p "$SWAN/conf.d" "$SWAN/x509" "$SWAN/x509ca" "$SWAN/private"

pki --gen --type rsa --size 3072 --outform pem > "$SWAN/private/custom-panel-ca.key"
pki --self --ca --lifetime 3650 \
  --in "$SWAN/private/custom-panel-ca.key" --type rsa \
  --dn "CN=Custom Panel CA" --outform pem \
  > "$SWAN/x509ca/custom-panel-ca.crt"

pki --gen --type rsa --size 3072 --outform pem > "$SWAN/private/server.key"
pki --pub --in "$SWAN/private/server.key" --type rsa |
  pki --issue --lifetime 1825 \
    --cacert "$SWAN/x509ca/custom-panel-ca.crt" \
    --cakey "$SWAN/private/custom-panel-ca.key" \
    --dn "CN=$SERVER_HOST" --san "$SERVER_HOST" \
    --flag serverAuth --flag ikeIntermediate \
    --outform pem > "$SWAN/x509/server.crt"
chmod 600 "$SWAN/private/"*.key

cat > "$SWAN/conf.d/custom-panel.conf" <<EOF
connections {
  custom-panel-eap {
    version = 2
    local_addrs = %any
    remote_addrs = %any
    pools = vpn4
    proposals = aes256-sha256-modp2048,aes128-sha256-modp2048
    fragmentation = yes
    mobike = yes
    dpd_delay = 30s

    local {
      auth = pubkey
      certs = server.crt
      id = $SERVER_HOST
    }

    remote {
      auth = eap-mschapv2
      eap_id = %any
    }

    children {
      net {
        local_ts = 0.0.0.0/0
        remote_ts = dynamic
        esp_proposals = aes256-sha256,aes128-sha256
        dpd_action = clear
        close_action = clear
      }
    }
  }
}

pools {
  vpn4 {
    addrs = 10.68.0.0/24
    dns = 1.1.1.1, 8.8.8.8
  }
}
EOF

cat > "$SWAN/conf.d/custom-panel-users.conf" <<'EOF'
secrets {
}
EOF
chmod 600 "$SWAN/conf.d/custom-panel-users.conf"

WAN_IF="$(ip route show default | awk '/default/ {print $5; exit}')"
[[ -n "$WAN_IF" ]] || die "Could not determine WAN interface."

iptables -t nat -C POSTROUTING -s 10.68.0.0/24 -o "$WAN_IF" -j MASQUERADE 2>/dev/null || \
  iptables -t nat -A POSTROUTING -s 10.68.0.0/24 -o "$WAN_IF" -j MASQUERADE
iptables -C FORWARD -s 10.68.0.0/24 -j ACCEPT 2>/dev/null || \
  iptables -A FORWARD -s 10.68.0.0/24 -j ACCEPT
iptables -C FORWARD -d 10.68.0.0/24 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || \
  iptables -A FORWARD -d 10.68.0.0/24 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

systemctl enable strongswan.service >/dev/null 2>&1 || true
systemctl restart strongswan.service
systemctl is-active --quiet strongswan.service || die "strongSwan failed to start."

LOAD_LOG="$(mktemp)"
if ! swanctl --load-all >"$LOAD_LOG" 2>&1; then
  cat "$LOAD_LOG"
  rm -f "$LOAD_LOG"
  die "swanctl failed to load configuration."
fi
grep -v "^plugin .*failed to load" "$LOAD_LOG" || true
grep -q "loaded connection 'custom-panel-eap'" "$LOAD_LOG" || {
  cat "$LOAD_LOG"
  rm -f "$LOAD_LOG"
  die "IKEv2 connection was not loaded."
}
rm -f "$LOAD_LOG"

cat > /etc/systemd/system/custom-panel-accounting.service <<EOF
[Unit]
Description=Custom Panel SSH and IKEv2 accounting
After=network-online.target strongswan.service
Wants=network-online.target strongswan.service

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
After=network-online.target strongswan.service
Wants=network-online.target strongswan.service

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
ReadWritePaths=$APP_DIR/data $APP_DIR/backups $APP_DIR/runtime /etc/swanctl /run
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

ufw allow OpenSSH >/dev/null 2>&1 || true
ufw allow 5000/tcp >/dev/null 2>&1 || true
ufw allow 500/udp >/dev/null 2>&1 || true
ufw allow 4500/udp >/dev/null 2>&1 || true
ufw --force enable >/dev/null 2>&1 || true

systemctl daemon-reload
systemctl enable custom-panel-accounting.service custom-panel.service >/dev/null
systemctl restart custom-panel-accounting.service custom-panel.service
sleep 2

systemctl is-active --quiet custom-panel-accounting.service || die "Accounting service failed."
systemctl is-active --quiet custom-panel.service || die "Panel service failed."
curl -fsS --max-time 10 http://127.0.0.1:5000/login >/dev/null || die "Panel health check failed."

echo
echo "Installed: http://$SERVER_HOST:5000"
echo "Credentials: $APP_DIR/admin-credentials.txt"
echo "Show credentials: sudo bash $APP_DIR/show-credentials.sh"
echo "Reset password: sudo bash $APP_DIR/reset-admin-password.sh"
