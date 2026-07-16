# Custom Panel v2.0 RC

Supported protocols:

- SSH
- WireGuard
- OpenVPN
- IKEv2 / strongSwan

## Important accounting behavior

WireGuard, OpenVPN, and IKEv2 use their protocol-native counters and store
independent cumulative totals in `protocol_usage`.

SSH sessions are shown as online/offline, but no fabricated traffic number is
stored. Exact per-user SSH tunnel accounting requires an eBPF/cgroup-based
collector or per-user network namespaces, which is outside this release.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/rima0222/ss/main/install.sh | sudo bash
```

The installer performs a clean reinstall by default and stores an emergency
backup under `/root/custom-panel-rescue-*`.

## IKEv2 client details

The downloaded IKEv2 text file shows:

- Server
- Remote ID
- Username
- Password
- CA certificate download path

For IP-based servers, the generated certificate includes the public IP as a SAN.
A domain name with a publicly trusted certificate is still preferable for broad
client compatibility.

## Diagnostics

```bash
sudo systemctl status custom-panel --no-pager
sudo systemctl status custom-panel-accounting --no-pager
sudo systemctl status wg-quick@wg0 --no-pager
sudo systemctl status openvpn-server@server --no-pager
sudo systemctl status strongswan --no-pager

sudo journalctl -u custom-panel-accounting -n 100 --no-pager
sudo wg show wg0 dump
sudo swanctl --list-sas
```
