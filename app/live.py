import re
import subprocess
import time

def _run(args, timeout=8):
    try:
        return subprocess.run(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        ).stdout
    except Exception:
        return ""

def ssh_online():
    """Return Linux usernames with an active sshd session."""
    out = _run(["ps", "-eo", "user=,comm="])
    users = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == "sshd":
            user = parts[0]
            if user not in {"root", "sshd", "nobody"}:
                users.add(user)
    return users

def ikev2_counters():
    """
    Return per-EAP-identity cumulative CHILD_SA counters from strongSwan.

    The parser supports the common `swanctl --list-sas` output format where
    the remote identity appears as:
        remote 'username'
    and CHILD_SA traffic appears as:
        1234 bytes_i, 5678 bytes_o
    """
    out = _run(["swanctl", "--list-sas"])
    result = {}
    current_user = None
    rx = tx = 0

    def commit():
        nonlocal rx, tx
        if current_user:
            item = result.setdefault(
                current_user,
                {"rx": 0, "tx": 0, "seen": int(time.time())},
            )
            item["rx"] += rx
            item["tx"] += tx
        rx = tx = 0

    for line in out.splitlines():
        remote = re.search(r"remote\s+'([^']+)'", line)
        if remote:
            commit()
            current_user = remote.group(1)
            continue

        match = re.search(r"(\d+)\s+bytes_i.*?(\d+)\s+bytes_o", line)
        if match and current_user:
            rx += int(match.group(1))
            tx += int(match.group(2))

    commit()
    return result
