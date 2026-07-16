#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR=/etc/custom-panel
REPO_URL="${CUSTOM_PANEL_REPO_URL:-https://github.com/YOUR_GITHUB_USERNAME/custom-panel.git}"
SERVER_HOST="${PANEL_SERVER_HOST:-$(curl -4fsS --max-time 10 https://api.ipify.org || hostname -I | awk '{print $1}')}"

[[ $EUID -eq 0 ]] || { echo 'Run with sudo.'; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv git curl ca-certificates openssh-server sqlite3 \
  wireguard-tools openvpn easy-rsa strongswan-swanctl strongswan-pki libcharon-extra-plugins \
  qrencode ufw iptables-persistent

systemctl enable --now ssh

if [[ -d "$APP_DIR/.git" ]]; then
  git -C "$APP_DIR" fetch --all --prune
  git -C "$APP_DIR" reset --hard origin/main
else
  rm -rf "$APP_DIR"
  git clone --depth=1 "$REPO_URL" "$APP_DIR"
fi

python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
mkdir -p "$APP_DIR/data" "$APP_DIR/backups" "$APP_DIR/runtime" /etc/custom-panel/protocols
chmod 750 "$APP_DIR/data" "$APP_DIR/backups" "$APP_DIR/runtime"

if [[ ! -f "$APP_DIR/.env" ]]; then
  ADMIN_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')
  SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
  cat > "$APP_DIR/.env" <<EOF
CUSTOM_PANEL_SECRET_KEY=$SECRET_KEY
CUSTOM_PANEL_ADMIN_USERNAME=admin
CUSTOM_PANEL_ADMIN_PASSWORD=$ADMIN_PASSWORD
CUSTOM_PANEL_DB=$APP_DIR/data/panel.db
CUSTOM_PANEL_SERVER_HOST=$SERVER_HOST
CUSTOM_PANEL_WG_INTERFACE=wg0
CUSTOM_PANEL_WG_PORT=51820
CUSTOM_PANEL_WG_SUBNET=10.66.0.0/24
CUSTOM_PANEL_OVPN_PORT=1194
CUSTOM_PANEL_IKE_CA=/etc/swanctl/x509ca/custom-panel-ca.crt
EOF
  printf 'Username: admin\nPassword: %s\n' "$ADMIN_PASSWORD" > "$APP_DIR/admin-credentials.txt"
  chmod 600 "$APP_DIR/.env" "$APP_DIR/admin-credentials.txt"
fi

# IP forwarding
cat > /etc/sysctl.d/99-custom-panel.conf <<EOF
net.ipv4.ip_forward=1
net.ipv6.conf.all.forwarding=1
EOF
sysctl --system >/dev/null

# WireGuard bootstrap
if [[ ! -f /etc/wireguard/wg0.conf ]]; then
  umask 077
  WG_PRIV=$(wg genkey)
  WG_PUB=$(printf '%s' "$WG_PRIV" | wg pubkey)
  WAN_IF=$(ip route show default | awk '/default/ {print $5; exit}')
  cat > /etc/wireguard/wg0.conf <<EOF
[Interface]
Address = 10.66.0.1/24
ListenPort = 51820
PrivateKey = $WG_PRIV
SaveConfig = false
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -A FORWARD -o wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o $WAN_IF -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -D FORWARD -o wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o $WAN_IF -j MASQUERADE
EOF
  printf '%s\n' "$WG_PUB" > /etc/wireguard/server.pub
fi
systemctl enable --now wg-quick@wg0

# OpenVPN bootstrap
OVPN=/etc/openvpn/server
mkdir -p "$OVPN/easy-rsa" "$OVPN/clients"
if [[ ! -f "$OVPN/ca.crt" ]]; then
  cp -a /usr/share/easy-rsa/* "$OVPN/easy-rsa/"
  pushd "$OVPN/easy-rsa" >/dev/null
  ./easyrsa --batch init-pki
  EASYRSA_REQ_CN='Custom Panel CA' ./easyrsa --batch build-ca nopass
  EASYRSA_CERT_EXPIRE=3650 ./easyrsa --batch build-server-full server nopass
  ./easyrsa --batch gen-dh
  openvpn --genkey secret "$OVPN/tls-crypt.key"
  cp pki/ca.crt pki/issued/server.crt pki/private/server.key pki/dh.pem "$OVPN/"
  popd >/dev/null
fi
cat > "$OVPN/server.conf" <<EOF
port 1194
proto udp
dev tun
user nobody
group nogroup
persist-key
persist-tun
topology subnet
server 10.67.0.0 255.255.255.0
push "redirect-gateway def1 bypass-dhcp"
push "dhcp-option DNS 1.1.1.1"
ca $OVPN/ca.crt
cert $OVPN/server.crt
key $OVPN/server.key
dh $OVPN/dh.pem
tls-crypt $OVPN/tls-crypt.key
auth SHA256
cipher AES-256-GCM
data-ciphers AES-256-GCM:CHACHA20-POLY1305
keepalive 10 120
status /run/openvpn-server/status.log 10
status-version 3
management 127.0.0.1 7505
verb 3
explicit-exit-notify 1
EOF
systemctl enable --now openvpn-server@server || true

# strongSwan / IKEv2 bootstrap
mkdir -p /etc/swanctl/{x509ca,x509,private,conf.d}
if [[ ! -f /etc/swanctl/x509ca/custom-panel-ca.crt ]]; then
  pki --gen --type rsa --size 3072 --outform pem > /etc/swanctl/private/custom-panel-ca.key
  pki --self --ca --lifetime 3650 --in /etc/swanctl/private/custom-panel-ca.key --type rsa \
    --dn 'CN=Custom Panel CA' --outform pem > /etc/swanctl/x509ca/custom-panel-ca.crt
  pki --gen --type rsa --size 3072 --outform pem > /etc/swanctl/private/server.key
  pki --pub --in /etc/swanctl/private/server.key --type rsa | pki --issue --lifetime 1825 \
    --cacert /etc/swanctl/x509ca/custom-panel-ca.crt \
    --cakey /etc/swanctl/private/custom-panel-ca.key \
    --dn "CN=$SERVER_HOST" --san "$SERVER_HOST" --flag serverAuth --flag ikeIntermediate \
    --outform pem > /etc/swanctl/x509/server.crt
fi
cat > /etc/swanctl/conf.d/custom-panel.conf <<EOF
connections {
  custom-panel-eap {
    version = 2
    pools = vpn4
    local_addrs = 0.0.0.0
    local { auth = pubkey; certs = server.crt; id = $SERVER_HOST }
    remote { auth = eap-mschapv2; eap_id = %any }
    children { net { local_ts = 0.0.0.0/0; esp_proposals = aes256gcm16-prfsha256-modp2048 } }
    proposals = aes256-sha256-modp2048
    send_cert = always
  }
}
pools { vpn4 { addrs = 10.68.0.0/24; dns = 1.1.1.1 } }
include conf.d/custom-panel-users.conf
EOF
[[ -f /etc/swanctl/conf.d/custom-panel-users.conf ]] || echo 'secrets { }' > /etc/swanctl/conf.d/custom-panel-users.conf
systemctl enable --now strongswan || systemctl enable --now strongswan-swanctl || true
swanctl --load-all >/dev/null 2>&1 || true

cat > /etc/systemd/system/custom-panel.service <<EOF
[Unit]
Description=Custom Panel
After=network-online.target ssh.service wg-quick@wg0.service
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/gunicorn --workers 2 --threads 4 --timeout 40 --bind 127.0.0.1:5000 'app:create_app()'
Restart=on-failure
RestartSec=3
PrivateTmp=true
ProtectHome=true
ProtectSystem=full
ReadWritePaths=$APP_DIR/data $APP_DIR/backups $APP_DIR/runtime /etc/wireguard /etc/openvpn /etc/swanctl /run
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

# Minimal Nginx-free public proxy using systemd socket is intentionally avoided. Bind panel via firewall-local port.
sed -i 's/--bind 127.0.0.1:5000/--bind 0.0.0.0:5000/' /etc/systemd/system/custom-panel.service

ufw allow OpenSSH >/dev/null || true
ufw allow 5000/tcp >/dev/null || true
ufw allow 51820/udp >/dev/null || true
ufw allow 1194/udp >/dev/null || true
ufw allow 500,4500/udp >/dev/null || true
ufw --force enable >/dev/null || true
systemctl daemon-reload
systemctl enable --now custom-panel

echo "Installed: http://$SERVER_HOST:5000"
echo "Credentials: $APP_DIR/admin-credentials.txt"
