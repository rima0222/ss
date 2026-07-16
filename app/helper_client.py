import json
import socket
from flask import current_app

def request_helper(action, username, password=None):
    payload = {"action": action, "username": username}
    if password is not None:
        payload["password"] = password

    path = current_app.config["HELPER_SOCKET"]
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(15)
        sock.connect(path)
        sock.sendall((json.dumps(payload, separators=(",", ":")) + "\n").encode())
        response = b""
        while not response.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                break
            response += chunk

    result = json.loads(response.decode() or "{}")
    if not result.get("ok"):
        raise RuntimeError(result.get("error", "Account helper failed"))
    return result
