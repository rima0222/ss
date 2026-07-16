import fcntl
import json
import os
import re
import socket
import subprocess
import time
from pathlib import Path

SOCKET_PATH = Path("/run/custom-panel/helper.sock")
LOCK_PATH = Path("/run/lock/custom-panel-passwd.lock")
USERNAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,30}$")

def run(args, input_text=None, check=True):
    last = None
    for attempt in range(4):
        result = subprocess.run(
            args,
            input=input_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        if result.returncode == 0 or not check:
            return result
        last = result
        message = ((result.stderr or "") + (result.stdout or "")).lower()
        if "cannot lock" not in message and "failure while writing" not in message:
            break
        time.sleep(1 + attempt)
    raise RuntimeError((last.stderr or last.stdout).strip() if last else "Linux account command failed")

def validate(username):
    if not USERNAME_RE.fullmatch(username):
        raise ValueError("Invalid username")

def exists(username):
    return run(["getent", "passwd", username], check=False).returncode == 0

def locked_call(action, username, password=None):
    validate(username)
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)

        if action == "upsert":
            if not password:
                raise ValueError("Password required")
            if not exists(username):
                run([
                    "useradd", "-M", "-N", "-G", "panelusers",
                    "-s", "/usr/local/bin/panel-hold", username,
                ])
            else:
                run([
                    "usermod", "-a", "-G", "panelusers",
                    "-s", "/usr/local/bin/panel-hold", username,
                ])
            run(["chpasswd"], f"{username}:{password}\n")
            run(["usermod", "-U", username], check=False)

        elif action == "pause":
            run(["usermod", "-L", username], check=False)
            run(["pkill", "-KILL", "-u", username], check=False)

        elif action == "resume":
            run(["usermod", "-U", username], check=False)

        elif action == "delete":
            run(["pkill", "-KILL", "-u", username], check=False)
            run(["userdel", "-r", username], check=False)

        else:
            raise ValueError("Unknown action")

def handle(conn):
    try:
        raw = b""
        while not raw.endswith(b"\n"):
            chunk = conn.recv(65536)
            if not chunk:
                break
            raw += chunk
        request = json.loads(raw.decode())
        locked_call(
            request.get("action", ""),
            request.get("username", ""),
            request.get("password"),
        )
        response = {"ok": True}
    except Exception as exc:
        response = {"ok": False, "error": str(exc)}
    conn.sendall((json.dumps(response, separators=(",", ":")) + "\n").encode())

def main():
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    SOCKET_PATH.unlink(missing_ok=True)

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(SOCKET_PATH))
        os.chmod(SOCKET_PATH, 0o660)
        import grp
        os.chown(SOCKET_PATH, 0, grp.getgrnam("custompanel").gr_gid)
        server.listen(64)
        while True:
            conn, _ = server.accept()
            with conn:
                handle(conn)

if __name__ == "__main__":
    main()
