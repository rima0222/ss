#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/etc/custom-panel"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash uninstall.sh"
  exit 1
fi

echo "This removes Custom Panel services/configuration."
echo "A rescue copy is preserved under /root."
read -r -p "Type REMOVE to continue: " answer
[[ "${answer}" == "REMOVE" ]] || { echo "Cancelled."; exit 1; }

stamp="$(date -u +%Y%m%d-%H%M%S)"
rescue="/root/custom-panel-rescue-${stamp}"
mkdir -p "${rescue}"

if [[ -d "${APP_DIR}" ]]; then
  cp -a "${APP_DIR}/data" "${rescue}/" 2>/dev/null || true
  cp -a "${APP_DIR}/backups" "${rescue}/" 2>/dev/null || true
  cp -a "${APP_DIR}/.env" "${rescue}/" 2>/dev/null || true
  cp -a "${APP_DIR}/admin-credentials.txt" "${rescue}/" 2>/dev/null || true
fi

systemctl disable --now custom-panel.service 2>/dev/null || true
systemctl disable --now custom-panel-wg-restore.service 2>/dev/null || true
systemctl disable --now wg-quick@wg0.service 2>/dev/null || true
systemctl disable --now openvpn-server@server.service 2>/dev/null || true

rm -f /etc/systemd/system/custom-panel.service
rm -f /etc/systemd/system/custom-panel-wg-restore.service
rm -rf "${APP_DIR}"
rm -f /etc/wireguard/wg0.conf
rm -f /etc/openvpn/server/server.conf
rm -rf /etc/openvpn/server/easy-rsa
rm -f /etc/swanctl/conf.d/custom-panel.conf
rm -f /etc/swanctl/conf.d/custom-panel-users.conf
ip link delete wg0 2>/dev/null || true

ufw --force delete allow 5000/tcp >/dev/null 2>&1 || true
ufw --force delete allow 51820/udp >/dev/null 2>&1 || true
ufw --force delete allow 1194/udp >/dev/null 2>&1 || true
ufw --force delete allow 500/udp >/dev/null 2>&1 || true
ufw --force delete allow 4500/udp >/dev/null 2>&1 || true


WAN_IF=$(ip route show default | awk '/default/ {print $5; exit}')
while iptables -t nat -C POSTROUTING -s 10.67.0.0/24 -o "$WAN_IF" -j MASQUERADE 2>/dev/null; do
  iptables -t nat -D POSTROUTING -s 10.67.0.0/24 -o "$WAN_IF" -j MASQUERADE || break
done

systemctl daemon-reload
systemctl reset-failed 2>/dev/null || true

tar -C /root -czf "${rescue}.tar.gz" "$(basename "${rescue}")" 2>/dev/null || true
echo "Removed. Rescue copy: ${rescue}.tar.gz"
