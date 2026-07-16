import fcntl
import re
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

LOCK = Path("/run/lock/custom-panel-users.lock")
USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,30}$")

@contextmanager
def locked():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

def run(args, input_text=None, check=True, retries=3):
    last = None
    for attempt in range(retries):
        result = subprocess.run(
            args, input=input_text, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=30, check=False,
        )
        if result.returncode == 0 or not check:
            return result
        last = result
        message = (result.stderr or result.stdout).lower()
        if "cannot lock" not in message and "failure while writing" not in message:
            break
        time.sleep(1 + attempt)
    raise RuntimeError((last.stderr or last.stdout).strip() if last else "system account command failed")

def validate(name):
    if not USER_RE.fullmatch(name):
        raise ValueError("نام کاربری نامعتبر است.")

def exists(name):
    return run(["getent", "passwd", name], check=False).returncode == 0

def create_or_update(name, password):
    validate(name)
    with locked():
        if not exists(name):
            run(["useradd", "-M", "-N", "-G", "panelusers", "-s", "/usr/local/bin/panel-hold", name])
        else:
            run(["usermod", "-a", "-G", "panelusers", "-s", "/usr/local/bin/panel-hold", name])
        run(["chpasswd"], f"{name}:{password}\n")
        run(["usermod", "-U", name], check=False)

def pause(name):
    validate(name)
    with locked():
        run(["usermod", "-L", name], check=False)
    run(["pkill", "-KILL", "-u", name], check=False)

def resume(name):
    validate(name)
    with locked():
        run(["usermod", "-U", name], check=False)

def delete(name):
    validate(name)
    run(["pkill", "-KILL", "-u", name], check=False)
    with locked():
        run(["userdel", "-r", name], check=False)
