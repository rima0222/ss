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
    systemctl disable --now custom-panel-accounting.service 2>/dev/null || true

    # Support service names used by different Ubuntu/strongSwan packages.
    for unit in strongswan.service strongswan-swanctl.service strongswan-starter.service charon-systemd.service; do
        systemctl disable --now "${unit}" 2>/dev/null || true
    done

    backup_existing_install
    remove_managed_linux_users

    echo "[*] Removing previous panel-owned files"
    rm -f /etc/systemd/system/custom-panel.service
    rm -f /etc/systemd/system/custom-panel-wg-restore.service
    rm -f /etc/systemd/system/custom-panel-accounting.service
    rm -rf "${APP_DIR}"

    # Remove only configurations/interfaces created by this project.
    rm -f /etc/swanctl/conf.d/custom-panel.conf
    rm -f /etc/swanctl/conf.d/custom-panel-users.conf
    rm -rf /etc/swanctl/x509/custom-panel
    rm -rf /etc/swanctl/x509ca/custom-panel
    rm -rf /etc/swanctl/private/custom-panel


    # Remove firewall rules by exact match, if they were previously inserted.

    # UFW rules are removed only for panel-specific ports.
    ufw --force delete allow 5000/tcp >/dev/null 2>&1 || true
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
  ufw strongswan-swanctl strongswan-pki charon-systemd libcharon-extra-plugins

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
CUSTOM_PANEL_IKE_REMOTE_ID=$SERVER_HOST
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

# IKEv2 / strongSwan bootstrap
SWAN=/etc/swanctl
mkdir -p "$SWAN/conf.d" "$SWAN/x509" "$SWAN/x509ca" "$SWAN/private"
if [[ ! -f "$SWAN/private/custom-panel-ca.key" ]]; then
  pki --gen --type rsa --size 3072 --outform pem > "$SWAN/private/custom-panel-ca.key"
  pki --self --ca --lifetime 3650 \
    --in "$SWAN/private/custom-panel-ca.key" --type rsa \
    --dn "CN=Custom Panel CA" --outform pem > "$SWAN/x509ca/custom-panel-ca.crt"

  pki --gen --type rsa --size 3072 --outform pem > "$SWAN/private/server.key"
  pki --pub --in "$SWAN/private/server.key" --type rsa |
    pki --issue --lifetime 1825 \
      --cacert "$SWAN/x509ca/custom-panel-ca.crt" \
      --cakey "$SWAN/private/custom-panel-ca.key" \
      --dn "CN=$SERVER_HOST" --san "$SERVER_HOST" \
      --flag serverAuth --flag ikeIntermediate \
      --outform pem > "$SWAN/x509/server.crt"
  chmod 600 "$SWAN/private/"*.key
fi

cat > "$SWAN/conf.d/custom-panel.conf" <<EOF
connections {
  custom-panel-eap {
    version = 2
    local_addrs = %any
    pools = vpn4
    proposals = aes256-sha256-modp2048,aes128-sha256-modp2048
    fragmentation = yes
    mobike = yes
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
        esp_proposals = aes256-sha256,aes128-sha256
        dpd_action = clear
      }
    }
  }
}
pools {
  vpn4 {
    addrs = 10.68.0.0/24
    dns = 1.1.1.1
  }
}
EOF

[[ -f "$SWAN/conf.d/custom-panel-users.conf" ]] || printf 'secrets {\n}\n' > "$SWAN/conf.d/custom-panel-users.conf"

WAN_IF=$(ip route show default | awk '/default/ {print $5; exit}')
iptables -t nat -C POSTROUTING -s 10.68.0.0/24 -o "$WAN_IF" -j MASQUERADE 2>/dev/null || \
  iptables -t nat -A POSTROUTING -s 10.68.0.0/24 -o "$WAN_IF" -j MASQUERADE
iptables -C FORWARD -s 10.68.0.0/24 -j ACCEPT 2>/dev/null || iptables -A FORWARD -s 10.68.0.0/24 -j ACCEPT
iptables -C FORWARD -d 10.68.0.0/24 -j ACCEPT 2>/dev/null || iptables -A FORWARD -d 10.68.0.0/24 -j ACCEPT

systemctl enable strongswan.service 2>/dev/null || true
systemctl restart strongswan.service
if ! systemctl is-active --quiet strongswan.service; then
  echo "[!] IKEv2 failed to start."
  journalctl -u strongswan.service -n 100 --no-pager || true
  exit 1
fi
SWANCTL_PLUGIN_DIR=/usr/lib/ipsec/plugins swanctl --load-all 2> >(grep -v "^plugin .*failed to load" >&2)


cat > /etc/systemd/system/custom-panel-accounting.service <<EOF
[Unit]
Description=Custom Panel traffic accounting

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/python -m app.accounting_worker
Restart=always
RestartSec=5
ProtectSystem=no
ReadWritePaths=$APP_DIR/data $APP_DIR/runtime /etc/swanctl /run

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/custom-panel.service <<EOF
[Unit]
Description=Custom Panel
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
ProtectSystem=no
# This service intentionally manages Linux users in /etc/passwd and /etc/shadow.
ReadWritePaths=$APP_DIR/data $APP_DIR/backups $APP_DIR/runtime /etc/swanctl /run
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

# Minimal Nginx-free public proxy using systemd socket is intentionally avoided. Bind panel via firewall-local port.
sed -i 's/--bind 127.0.0.1:5000/--bind 0.0.0.0:5000/' /etc/systemd/system/custom-panel.service

# Permit routed VPN traffic through UFW without changing the global forward policy.
WAN_IF=$(ip route show default | awk '/default/ {print $5; exit}')

ufw allow OpenSSH >/dev/null || true
ufw allow 5000/tcp >/dev/null || true
ufw allow 500/udp
ufw allow 4500/udp >/dev/null || true
ufw --force enable >/dev/null || true
systemctl daemon-reload
systemctl enable --now custom-panel-accounting
systemctl restart custom-panel-accounting
systemctl enable --now custom-panel
systemctl restart custom-panel


if ! systemctl is-active --quiet strongswan.service; then
  echo "[!] strongSwan is not active after installation."
  journalctl -u strongswan.service -n 100 --no-pager || true
  exit 1
fi
if ! systemctl is-active --quiet custom-panel-accounting.service; then
  echo "[!] Accounting service is not active."
  journalctl -u custom-panel-accounting.service -n 100 --no-pager || true
  exit 1
fi
if ! systemctl is-active --quiet custom-panel.service; then
  echo "[!] Panel service is not active."
  journalctl -u custom-panel.service -n 100 --no-pager || true
  exit 1
fi

echo "Installed: http://$SERVER_HOST:5000"
echo "Credentials: $APP_DIR/admin-credentials.txt"
echo "Show credentials: sudo bash $APP_DIR/show-credentials.sh"
echo "Reset password: sudo bash $APP_DIR/reset-admin-password.sh"
