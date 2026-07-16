import json
import re
import subprocess
import time
from pathlib import Path

def _run(args, timeout=8):
    try:
        return subprocess.run(
            args, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=timeout, check=False
        ).stdout
    except Exception:
        return ""

def ssh_online():
    out = _run(["ps", "-eo", "user=,comm="])
    return {
        parts[0] for line in out.splitlines()
        if len((parts := line.split())) == 2
        and parts[1] == "sshd"
        and parts[0] not in {"root", "sshd", "nobody"}
    }

def wireguard_counters(interface="wg0"):
    out = _run(["wg", "show", interface, "dump"])
    result = {}
    for index, line in enumerate(out.splitlines()):
        if index == 0:
            continue
        cols = line.split("\t")
        if len(cols) >= 7:
            try:
                result[cols[0]] = {
                    "rx": int(cols[5] or 0),
                    "tx": int(cols[6] or 0),
                    "seen": int(cols[4] or 0),
                }
            except ValueError:
                pass
    return result

def openvpn_counters():
    candidates = [
        Path("/run/openvpn-server/status.log"),
        Path("/run/openvpn-server/status-server.log"),
    ]
    path = next((p for p in candidates if p.exists()), None)
    if not path:
        return {}
    result = {}
    for line in path.read_text(errors="ignore").splitlines():
        if line.startswith("CLIENT_LIST\t"):
            cols = line.split("\t")
        elif line.startswith("CLIENT_LIST,"):
            cols = line.split(",")
        else:
            continue
        if len(cols) < 8:
            continue
        try:
            result[cols[1].strip()] = {
                "rx": int(cols[6] or 0),
                "tx": int(cols[7] or 0),
                "seen": int(time.time()),
            }
        except ValueError:
            pass
    return result

def ikev2_counters():
    """
    Parse strongSwan's human-readable SA list. The output contains the remote
    EAP identity and CHILD_SA byte counters. Unknown layouts are skipped.
    """
    out = _run(["swanctl", "--list-sas"])
    result = {}
    current_user = None
    rx = tx = 0

    def commit():
        nonlocal current_user, rx, tx
        if current_user:
            item = result.setdefault(current_user, {"rx": 0, "tx": 0, "seen": int(time.time())})
            item["rx"] += rx
            item["tx"] += tx
        rx = tx = 0

    for line in out.splitlines():
        remote = re.search(r"remote\s+'([^']+)'", line)
        if remote:
            commit()
            current_user = remote.group(1)
            continue

        # Typical strongSwan CHILD_SA line:
        # 1234 bytes_i, 5678 bytes_o
        match = re.search(r"(\d+)\s+bytes_i.*?(\d+)\s+bytes_o", line)
        if match and current_user:
            rx += int(match.group(1))
            tx += int(match.group(2))

    commit()
    return result
