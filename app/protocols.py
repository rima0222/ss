import fcntl
import ipaddress
import json
import os
import re
import socket
import subprocess
from pathlib import Path

from flask import current_app

USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,30}$")
ACCOUNT_LOCK = Path("/run/lock/custom-panel-accounts.lock")
PROTOCOL_LOCK = Path("/run/lock/custom-panel-protocols.lock")

class file_lock:
    def __init__(self, path):
        self.path = path
    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.f = self.path.open("a+")
        fcntl.flock(self.f.fileno(), fcntl.LOCK_EX)
        return self
    def __exit__(self, *_):
        fcntl.flock(self.f.fileno(), fcntl.LOCK_UN)
        self.f.close()

def run(args, input_text=None, check=True, timeout=30):
    result = subprocess.run(
        args,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"command failed: {args[0]}")
    return result

def valid_user(name):
    if not USER_RE.fullmatch(name):
        raise ValueError("نام کاربری نامعتبر است.")

class SSH:
    name = "ssh"
    def create(self, user):
        valid_user(user["username"])
        name = user["username"]
        with file_lock(ACCOUNT_LOCK):
            exists = run(["getent", "passwd", name], check=False).returncode == 0
            if not exists:
                run(["useradd", "-M", "-N", "-s", "/usr/sbin/nologin", name])
            else:
                run(["usermod", "-s", "/usr/sbin/nologin", name])
            run(["chpasswd"], f"{name}:{user['password']}\n")
            run(["usermod", "-U", name])
        return {"identifier": name, "config": {}}
    update = create
    def pause(self, user, meta=None):
        with file_lock(ACCOUNT_LOCK):
            run(["usermod", "-L", user["username"]], check=False)
        run(["pkill", "-KILL", "-u", user["username"]], check=False)
    def resume(self, user, meta=None):
        with file_lock(ACCOUNT_LOCK):
            run(["usermod", "-U", user["username"]], check=False)
    def delete(self, user, meta=None):
        run(["pkill", "-KILL", "-u", user["username"]], check=False)
        with file_lock(ACCOUNT_LOCK):
            run(["userdel", "-r", user["username"]], check=False)
    def client(self, user, meta=None):
        content = (
            f"Host: {current_app.config['SERVER_HOST']}\n"
            f"Port: 22\nUsername: {user['username']}\nPassword: {user['password']}\n"
        )
        return {"filename": f"{user['username']}-ssh.txt", "content": content}

class WireGuard:
    name = "wireguard"
    state = Path("/etc/wireguard/custom-panel-peers.json")

    def _all(self):
        try:
            return json.loads(self.state.read_text())
        except Exception:
            return {}

    def _save(self, data):
        self.state.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.state)

    def create(self, user):
        with file_lock(PROTOCOL_LOCK):
            data = self._all()
            name = user["username"]
            if name in data:
                item = data[name]
            else:
                private = run(["wg", "genkey"]).stdout.strip()
                public = run(["wg", "pubkey"], private + "\n").stdout.strip()
                used = {x["address"] for x in data.values()}
                address = next(
                    (str(ip) for ip in ipaddress.ip_network("10.66.0.0/24").hosts()
                     if str(ip) != "10.66.0.1" and str(ip) not in used),
                    None,
                )
                if not address:
                    raise RuntimeError("ظرفیت WireGuard تکمیل است.")
                item = {"private_key": private, "public_key": public, "address": address}
                data[name] = item
                self._save(data)

            run([
                "wg", "set", current_app.config["WG_INTERFACE"],
                "peer", item["public_key"],
                "allowed-ips", item["address"] + "/32",
            ])
            return {"identifier": item["public_key"], "config": item}

    def pause(self, user, meta=None):
        item = (meta or {}).get("config") or self._all().get(user["username"])
        if item:
            run(["wg", "set", current_app.config["WG_INTERFACE"], "peer", item["public_key"], "remove"], check=False)

    def resume(self, user, meta=None):
        item = (meta or {}).get("config") or self._all().get(user["username"])
        if item:
            run([
                "wg", "set", current_app.config["WG_INTERFACE"],
                "peer", item["public_key"],
                "allowed-ips", item["address"] + "/32",
            ], check=False)

    def delete(self, user, meta=None):
        with file_lock(PROTOCOL_LOCK):
            data = self._all()
            item = data.pop(user["username"], None)
            if item:
                run(["wg", "set", current_app.config["WG_INTERFACE"], "peer", item["public_key"], "remove"], check=False)
                self._save(data)

    def update(self, user, meta=None):
        return None

    def client(self, user, meta=None):
        item = (meta or {}).get("config") or self._all().get(user["username"])
        if not item:
            raise RuntimeError("پروفایل WireGuard پیدا نشد.")
        server_public = Path("/etc/wireguard/server.pub").read_text().strip()
        content = f"""[Interface]
PrivateKey = {item['private_key']}
Address = {item['address']}/32
DNS = 1.1.1.1

[Peer]
PublicKey = {server_public}
Endpoint = {current_app.config['SERVER_HOST']}:{current_app.config['WG_PORT']}
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
"""
        return {"filename": f"{user['username']}.conf", "content": content}

class OpenVPN:
    name = "openvpn"
    base = Path("/etc/openvpn/server")

    def _disconnect(self, name):
        try:
            password = (self.base / "management.pass").read_text().strip()
            with socket.create_connection(("127.0.0.1", 7505), timeout=3) as sock:
                sock.settimeout(3)
                greeting = sock.recv(4096)
                if b"PASSWORD:" in greeting:
                    sock.sendall((password + "\n").encode())
                    sock.recv(4096)
                sock.sendall(f"kill {name}\nquit\n".encode())
        except Exception:
            pass

    def create(self, user):
        name = user["username"]
        valid_user(name)
        er = self.base / "easy-rsa"
        with file_lock(PROTOCOL_LOCK):
            if not (er / "pki" / "issued" / f"{name}.crt").exists():
                run([str(er / "easyrsa"), "--batch", "build-client-full", name, "nopass"], timeout=120)
            (self.base / "clients" / f"{name}.disabled").unlink(missing_ok=True)
        return {"identifier": name, "config": {"common_name": name}}

    def pause(self, user, meta=None):
        marker = self.base / "clients" / f"{user['username']}.disabled"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("disabled\n")
        self._disconnect(user["username"])

    def resume(self, user, meta=None):
        (self.base / "clients" / f"{user['username']}.disabled").unlink(missing_ok=True)

    def delete(self, user, meta=None):
        marker = self.base / "clients" / f"{user['username']}.disabled"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("deleted\n")
        self._disconnect(user["username"])

    def update(self, user, meta=None):
        return None

    def client(self, user, meta=None):
        name = user["username"]
        er = self.base / "easy-rsa"
        def read(path):
            return Path(path).read_text().strip()
        content = f"""client
dev tun
proto udp
remote {current_app.config['SERVER_HOST']} {current_app.config['OVPN_PORT']}
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server
auth SHA256
data-ciphers AES-256-GCM:CHACHA20-POLY1305
auth-nocache
verb 3
<ca>
{read(self.base/'ca.crt')}
</ca>
<cert>
{read(er/'pki'/'issued'/f'{name}.crt')}
</cert>
<key>
{read(er/'pki'/'private'/f'{name}.key')}
</key>
<tls-crypt>
{read(self.base/'tls-crypt.key')}
</tls-crypt>
"""
        return {"filename": f"{name}.ovpn", "content": content}

class IKEv2:
    name = "ikev2"
    users_file = Path("/etc/swanctl/conf.d/custom-panel-users.conf")
    state_file = Path("/etc/swanctl/custom-panel-users.json")

    def _all(self):
        try:
            return json.loads(self.state_file.read_text())
        except Exception:
            return {}

    def _write(self, data):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.state_file)

        lines = ["secrets {"]
        for name, item in sorted(data.items()):
            if item.get("disabled"):
                continue
            lines += [
                f"  eap-{name} {{",
                f"    id = {name}",
                f"    secret = \"{item['password'].replace(chr(34), '')}\"",
                "  }",
            ]
        lines.append("}")
        tmp_conf = self.users_file.with_suffix(".tmp")
        tmp_conf.write_text("\n".join(lines) + "\n")
        os.chmod(tmp_conf, 0o600)
        os.replace(tmp_conf, self.users_file)
        run(["swanctl", "--load-creds"], check=False)

    def create(self, user):
        valid_user(user["username"])
        with file_lock(PROTOCOL_LOCK):
            data = self._all()
            data[user["username"]] = {"password": user["password"], "disabled": False}
            self._write(data)
        return {"identifier": user["username"], "config": {"eap_id": user["username"]}}

    update = create

    def pause(self, user, meta=None):
        with file_lock(PROTOCOL_LOCK):
            data = self._all()
            if user["username"] in data:
                data[user["username"]]["disabled"] = True
                self._write(data)
        # Reloading credentials prevents new logins. Existing SAs are terminated
        # by connection name; this may disconnect other IKEv2 users too.
        run(["swanctl", "--terminate", "--ike", "custom-panel-eap"], check=False)

    def resume(self, user, meta=None):
        with file_lock(PROTOCOL_LOCK):
            data = self._all()
            if user["username"] in data:
                data[user["username"]]["disabled"] = False
                data[user["username"]]["password"] = user["password"]
                self._write(data)

    def delete(self, user, meta=None):
        with file_lock(PROTOCOL_LOCK):
            data = self._all()
            data.pop(user["username"], None)
            self._write(data)
        run(["swanctl", "--terminate", "--ike", "custom-panel-eap"], check=False)

    def client(self, user, meta=None):
        ca = Path("/etc/swanctl/x509ca/custom-panel-ca.crt")
        content = (
            f"Server: {current_app.config['SERVER_HOST']}\n"
            f"VPN type: IKEv2\n"
            f"Remote ID: {current_app.config['IKE_REMOTE_ID']}\n"
            f"Username: {user['username']}\n"
            f"Password: {user['password']}\n"
            f"CA certificate: /users/{user['username']}/config/ikev2-ca\n"
        )
        return {"filename": f"{user['username']}-ikev2.txt", "content": content}

REGISTRY = {
    "ssh": SSH(),
    "wireguard": WireGuard(),
    "openvpn": OpenVPN(),
    "ikev2": IKEv2(),
}
