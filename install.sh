#!/usr/bin/env bash
set -Eeuo pipefail
# ---------------------------------------------------------------------------
# Clean reinstall
# ---------------------------------------------------------------------------
# This installer intentionally replaces previous Custom Panel installations.
# Before removal it stores an emergency copy under /root/custom-panel-rescue-*.
#
# It does NOT remove the current root/administrator SSH account and does not
# rewrite the main OpenSSH server configuration.
#
# Set CUSTOM_PANEL_CLEAN_INSTALL=0 to perform an in-place update instead.
CLEAN_INSTALL="${CUSTOM_PANEL_CLEAN_INSTALL:-1}"
APP_DIR="${APP_DIR:-/etc/custom-panel}"
SERVICE_NAME="${SERVICE_NAME:-custom-panel}"

backup_existing_install() {
    if [[ ! -e "${APP_DIR}" ]]; then
        return 0
    fi

    local stamp rescue
    stamp="$(date -u +%Y%m%d-%H%M%S)"
    rescue="/root/custom-panel-rescue-${stamp}"
    mkdir -p "${rescue}"

    echo "[*] Saving emergency copy to ${rescue}"

    for item in \
        "${APP_DIR}/data" \
        "${APP_DIR}/backups" \
        "${APP_DIR}/.env" \
        "${APP_DIR}/admin-credentials.txt"; do
        if [[ -e "${item}" ]]; then
            cp -a "${item}" "${rescue}/"
        fi
    done

    if [[ -f "${APP_DIR}/data/panel.db" ]] && command -v sqlite3 >/dev/null 2>&1; then
        sqlite3 "${APP_DIR}/data/panel.db" ".backup '${rescue}/panel.db'" 2>/dev/null || true

        # Save usernames managed by the panel so only those accounts can be
        # removed. Failure is harmless and leaves Linux accounts untouched.
        sqlite3 -noheader "${APP_DIR}/data/panel.db" \
            "SELECT username FROM users WHERE username IS NOT NULL;" \
            > "${rescue}/managed-users.txt" 2>/dev/null || true
    fi

    tar -C /root -czf "${rescue}.tar.gz" "$(basename "${rescue}")" 2>/dev/null || true
}

remove_managed_linux_users() {
    local rescue_dir users_file username
    rescue_dir="$(find /root -maxdepth 1 -type d -name 'custom-panel-rescue-*' -printf '%T@ %p\n' 2>/dev/null \
        | sort -nr | head -n1 | cut -d' ' -f2- || true)"
    users_file="${rescue_dir}/managed-users.txt"

    [[ -f "${users_file}" ]] || return 0

    while IFS= read -r username; do
        [[ -n "${username}" ]] || continue

        # Strict validation prevents command/argument injection.
        if [[ ! "${username}" =~ ^[a-z_][a-z0-9_-]{0,30}$ ]]; then
            echo "[!] Skipping invalid stored username: ${username}"
            continue
        fi

        case "${username}" in
            root|ubuntu|admin|sshd|nobody)
                echo "[!] Protected system account was not removed: ${username}"
                continue
                ;;
        esac

        if getent passwd "${username}" >/dev/null 2>&1; then
            pkill -KILL -u "${username}" 2>/dev/null || true
            userdel -r "${username}" 2>/dev/null || userdel "${username}" 2>/dev/null || true
        fi
    done < "${users_file}"
}

clean_previous_install() {
    echo "[*] Stopping previous Custom Panel services"

    systemctl disable --now custom-panel.service 2>/dev/null || true
    systemctl disable --now custom-panel-wg-restore.service 2>/dev/null || true
    systemctl disable --now wg-quick@wg0.service 2>/dev/null || true
    systemctl disable --now openvpn-server@server.service 2>/dev/null || true

    # Support service names used by different Ubuntu/strongSwan packages.
    for unit in strongswan.service strongswan-swanctl.service strongswan-starter.service charon-systemd.service; do
        systemctl disable --now "${unit}" 2>/dev/null || true
    done

    backup_existing_install
    remove_managed_linux_users

    echo "[*] Removing previous panel-owned files"
    rm -f /etc/systemd/system/custom-panel.service
    rm -f /etc/systemd/system/custom-panel-wg-restore.service
    rm -rf "${APP_DIR}"

    # Remove only configurations/interfaces created by this project.
    rm -f /etc/wireguard/wg0.conf
    rm -f /etc/openvpn/server/server.conf
    rm -rf /etc/openvpn/server/easy-rsa
    rm -f /etc/swanctl/conf.d/custom-panel.conf
    rm -f /etc/swanctl/conf.d/custom-panel-users.conf
    rm -rf /etc/swanctl/x509/custom-panel
    rm -rf /etc/swanctl/x509ca/custom-panel
    rm -rf /etc/swanctl/private/custom-panel

    ip link delete wg0 2>/dev/null || true

    # Remove firewall rules by exact match, if they were previously inserted.
    while iptables -C FORWARD -i wg0 -j ACCEPT 2>/dev/null; do
        iptables -D FORWARD -i wg0 -j ACCEPT 2>/dev/null || break
    done
    while iptables -C FORWARD -o wg0 -j ACCEPT 2>/dev/null; do
        iptables -D FORWARD -o wg0 -j ACCEPT 2>/dev/null || break
    done
    while iptables -C FORWARD -i tun0 -j ACCEPT 2>/dev/null; do
        iptables -D FORWARD -i tun0 -j ACCEPT 2>/dev/null || break
    done
    while iptables -C FORWARD -o tun0 -j ACCEPT 2>/dev/null; do
        iptables -D FORWARD -o tun0 -j ACCEPT 2>/dev/null || break
    done

    # UFW rules are removed only for panel-specific ports.
    ufw --force delete allow 5000/tcp >/dev/null 2>&1 || true
    ufw --force delete allow 51820/udp >/dev/null 2>&1 || true
    ufw --force delete allow 1194/udp >/dev/null 2>&1 || true
    ufw --force delete allow 500/udp >/dev/null 2>&1 || true
    ufw --force delete allow 4500/udp >/dev/null 2>&1 || true

    systemctl daemon-reload
    systemctl reset-failed 2>/dev/null || true
}

if [[ "${CLEAN_INSTALL}" == "1" ]]; then
    clean_previous_install
fi
APP_DIR=/etc/custom-panel
REPO_URL="${CUSTOM_PANEL_REPO_URL:-https://github.com/rima0222/ss.git}"
SERVER_HOST="${PANEL_SERVER_HOST:-$(curl -4fsS --max-time 10 https://api.ipify.org || hostname -I | awk '{print $1}')}"

[[ $EUID -eq 0 ]] || { echo 'Run with sudo.'; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv git curl ca-certificates openssh-server sqlite3 \
  wireguard-tools openvpn easy-rsa strongswan-swanctl strongswan-pki charon-systemd libcharon-extra-plugins \
  qrencode ufw

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
systemctl enable --now strongswan.service 2>/dev/null || systemctl enable --now charon-systemd.service 2>/dev/null || true
swanctl --load-all >/dev/null 2>&1 || true

cat > /etc/systemd/system/custom-panel-wg-restore.service <<EOF
[Unit]
Description=Restore Custom Panel WireGuard peers
After=wg-quick@wg0.service
Requires=wg-quick@wg0.service

[Service]
Type=oneshot
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/app/wg_restore.py
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

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

# Permit routed VPN traffic through UFW without changing the global forward policy.
WAN_IF=$(ip route show default | awk '/default/ {print $5; exit}')
ufw route allow in on wg0 out on "$WAN_IF" >/dev/null 2>&1 || true
ufw route allow in on tun0 out on "$WAN_IF" >/dev/null 2>&1 || true
ufw route allow from 10.68.0.0/24 to any >/dev/null 2>&1 || true

ufw allow OpenSSH >/dev/null || true
ufw allow 5000/tcp >/dev/null || true
ufw allow 51820/udp >/dev/null || true
ufw allow 1194/udp >/dev/null || true
ufw allow 500,4500/udp >/dev/null || true
ufw --force enable >/dev/null || true
systemctl daemon-reload
systemctl enable --now custom-panel-wg-restore.service
systemctl restart custom-panel-wg-restore.service || true
systemctl enable --now custom-panel
systemctl restart custom-panel

echo "Installed: http://$SERVER_HOST:5000"
echo "Credentials: $APP_DIR/admin-credentials.txt"
