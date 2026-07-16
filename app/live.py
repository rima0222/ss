import json
import subprocess
import time
from pathlib import Path

WG_PEERS = Path('/etc/wireguard/custom-panel-peers.json')
OVPN_STATUS_CANDIDATES = [
    Path('/run/openvpn-server/status.log'),
    Path('/run/openvpn-server/status-server.log'),
]


def _run(args, timeout=5):
    try:
        return subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              timeout=timeout, check=False).stdout
    except Exception:
        return ''


def ssh_online():
    """Return usernames that currently own an sshd session process."""
    out = _run(['ps', '-eo', 'user=,comm='])
    users = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == 'sshd' and parts[0] not in {'root', 'sshd', 'nobody'}:
            users.add(parts[0])
    return users


def wireguard_stats(interface='wg0', online_window=180):
    try:
        peers = json.loads(WG_PEERS.read_text())
    except Exception:
        peers = {}
    pub_to_name = {v.get('public_key'): name for name, v in peers.items() if v.get('public_key')}
    out = _run(['wg', 'show', interface, 'dump'])
    now = int(time.time())
    result = {}
    for i, line in enumerate(out.splitlines()):
        if i == 0:
            continue
        cols = line.split('\t')
        if len(cols) < 8:
            continue
        pub = cols[0]
        name = pub_to_name.get(pub)
        if not name:
            continue
        try:
            handshake = int(cols[4] or 0)
            rx = int(cols[5] or 0)
            tx = int(cols[6] or 0)
        except ValueError:
            handshake = rx = tx = 0
        result[name] = {
            'online': bool(handshake and now - handshake <= online_window),
            'last_handshake': handshake,
            'rx_bytes': rx,
            'tx_bytes': tx,
        }
    return result


def openvpn_stats():
    path = next((p for p in OVPN_STATUS_CANDIDATES if p.exists()), None)
    if not path:
        return {}
    result = {}
    try:
        lines = path.read_text(errors='ignore').splitlines()
    except Exception:
        return result
    for line in lines:
        # status-version 3: CLIENT_LIST,Common Name,Real Address,Virtual Address,...,Bytes Received,Bytes Sent,...
        if not line.startswith('CLIENT_LIST,'):
            continue
        cols = line.split(',')
        if len(cols) < 8:
            continue
        name = cols[1].strip()
        if not name or name == 'UNDEF':
            continue
        try:
            rx = int(cols[6] or 0)
            tx = int(cols[7] or 0)
        except ValueError:
            rx = tx = 0
        result[name] = {'online': True, 'rx_bytes': rx, 'tx_bytes': tx}
    return result



def collect_live(users, wg_interface='wg0'):
    ssh = ssh_online()
    wg = wireguard_stats(wg_interface)
    ovpn = openvpn_stats()
    result = {}
    for u in users:
        name = u['username']
        protocols = [p for p in (u.get('protocols') or '').split(',') if p]
        pstats = {}
        total_rx = total_tx = 0
        any_online = False
        for protocol in protocols:
            if protocol == 'ssh':
                stat = {'online': name in ssh, 'rx_bytes': 0, 'tx_bytes': 0}
            elif protocol == 'wireguard':
                stat = wg.get(name, {'online': False, 'rx_bytes': 0, 'tx_bytes': 0, 'last_handshake': 0})
            elif protocol == 'openvpn':
                stat = ovpn.get(name, {'online': False, 'rx_bytes': 0, 'tx_bytes': 0})
            else:
                stat = {'online': False, 'rx_bytes': 0, 'tx_bytes': 0}
            any_online = any_online or stat['online']
            total_rx += stat.get('rx_bytes', 0)
            total_tx += stat.get('tx_bytes', 0)
            pstats[protocol] = stat
        result[name] = {
            'online': any_online,
            'rx_bytes': total_rx,
            'tx_bytes': total_tx,
            'protocols': pstats,
        }
    return result
