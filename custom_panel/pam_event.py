#!/usr/bin/env python3
import json
import os
import socket
import time
import uuid
from pathlib import Path

SOCKET = os.getenv("CP_MANAGER_SOCKET", "/run/custom-panel/manager.sock")
SPOOL = Path("/run/custom-panel/pam-spool")

def event():
    pam_type = os.getenv("PAM_TYPE", "")
    if pam_type not in {"open_session", "close_session"}:
        return
    payload = {
        "method": "pam.event",
        "params": {
            "event": "open" if pam_type == "open_session" else "close",
            "username": os.getenv("PAM_USER", ""),
            "rhost": os.getenv("PAM_RHOST", ""),
            "tty": os.getenv("PAM_TTY", ""),
            "session_key": f"{os.getenv('PAM_USER','')}:{os.getppid()}:{os.getenv('PAM_TTY','')}",
            "time": int(time.time()),
        },
    }
    raw = (json.dumps(payload, separators=(",", ":")) + "\n").encode()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.35)
            sock.connect(SOCKET)
            sock.sendall(raw)
            sock.recv(4096)
    except Exception:
        try:
            SPOOL.mkdir(parents=True, exist_ok=True)
            target = SPOOL / f"{int(time.time()*1000)}-{uuid.uuid4().hex}.json"
            target.write_text(json.dumps(payload), encoding="utf-8")
            os.chmod(target, 0o660)
        except Exception:
            pass

if __name__ == "__main__":
    event()
