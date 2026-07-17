import asyncio
import json
import os
import secrets
import subprocess
import time
from collections import defaultdict
from pathlib import Path

from werkzeug.security import generate_password_hash

from .crypto import decrypt_text, encrypt_text
from .db import connect, initialize, transaction
from .ipc import request
from .settings import settings
from .validation import as_float, as_int, validate_password, validate_username

class Manager:
    def __init__(self):
        initialize(settings.db_path)
        self.gateway_seen = 0
        self.gateway_sessions = {}
        self.pam_sessions = defaultdict(set)
        self.process_sessions = {}
        self.lock = asyncio.Lock()

    def helper(self, payload):
        return request(settings.helper_socket, payload, timeout=40)

    def rows(self):
        with connect(settings.db_path) as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM users ORDER BY id DESC")]

    def mappings(self):
        return [
            {"username": row["username"], "backend_port": row["backend_port"]}
            for row in self.rows()
        ]

    async def sync_backend(self):
        await asyncio.to_thread(
            self.helper,
            {"action": "backend.sync", "mappings": self.mappings()},
        )

    def allocate(self, column, start, end):
        with connect(settings.db_path) as conn:
            used = {
                int(row[column])
                for row in conn.execute(
                    f"SELECT {column} FROM users WHERE {column} IS NOT NULL"
                )
            }
        for number in range(start, end + 1):
            if number not in used:
                return number
        raise RuntimeError(f"No free {column} is available")

    def audit(self, conn, action, subject="", detail=""):
        conn.execute(
            "INSERT INTO audit_log(action,subject,detail,created_at) VALUES(?,?,?,?)",
            (action, subject, detail, int(time.time())),
        )

    def active_config(self):
        now = int(time.time())
        with connect(settings.db_path) as conn:
            rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT id,username,tcp_enabled,ws_enabled,tcp_port,
                           backend_port,ws_token,paused,expires_at,status
                    FROM users
                    WHERE paused=0 AND expires_at>? AND status='active'
                    ORDER BY id
                    """,
                    (now,),
                )
            ]
        return {
            "generation": now,
            "ws_port": settings.ws_port,
            "users": rows,
        }

    async def gateway_metrics(self, params):
        now = int(time.time())
        deltas = params.get("deltas", [])
        sessions = params.get("sessions", {})
        with transaction(settings.db_path, immediate=True) as conn:
            for item in deltas:
                user_id = int(item["user_id"])
                kind = item["kind"]
                down = max(0, int(item.get("download", 0)))
                up = max(0, int(item.get("upload", 0)))
                if kind == "tcp":
                    conn.execute(
                        """
                        UPDATE users SET
                            download_bytes=download_bytes+?,
                            upload_bytes=upload_bytes+?,
                            tcp_download_bytes=tcp_download_bytes+?,
                            tcp_upload_bytes=tcp_upload_bytes+?,
                            updated_at=?
                        WHERE id=?
                        """,
                        (down, up, down, up, now, user_id),
                    )
                elif kind == "ws":
                    conn.execute(
                        """
                        UPDATE users SET
                            download_bytes=download_bytes+?,
                            upload_bytes=upload_bytes+?,
                            ws_download_bytes=ws_download_bytes+?,
                            ws_upload_bytes=ws_upload_bytes+?,
                            updated_at=?
                        WHERE id=?
                        """,
                        (down, up, down, up, now, user_id),
                    )

        async with self.lock:
            self.gateway_seen = now
            self.gateway_sessions = {
                str(key): value for key, value in sessions.items()
            }

        await self.enforce()
        return {"accepted": True, "time": now}

    async def pam_event(self, params):
        username = params.get("username", "")
        if not username:
            return {"accepted": False}
        key = params.get("session_key") or secrets.token_hex(8)
        async with self.lock:
            if params.get("event") == "open":
                self.pam_sessions[username].add(key)
            else:
                self.pam_sessions[username].discard(key)
        return {"accepted": True}

    def process_session_counts(self):
        result = subprocess.run(
            ["ps", "-eo", "user=,args="],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
        counts = defaultdict(int)
        marker = "/usr/local/lib/custom-panel/panel-hold"
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or marker not in line:
                continue
            username = line.split(None, 1)[0]
            counts[username] += 1
        return dict(counts)

    async def reconcile_sessions(self):
        while True:
            try:
                counts = await asyncio.to_thread(self.process_session_counts)
                async with self.lock:
                    self.process_sessions = counts
            except Exception:
                pass
            await asyncio.sleep(2)

    async def drain_pam_spool(self):
        spool = Path("/run/custom-panel/pam-spool")
        while True:
            try:
                spool.mkdir(parents=True, exist_ok=True)
                for path in sorted(spool.glob("*.json"))[:200]:
                    try:
                        payload = json.loads(path.read_text(encoding="utf-8"))
                        await self.pam_event(payload.get("params", {}))
                        path.unlink(missing_ok=True)
                    except Exception:
                        pass
            except Exception:
                pass
            await asyncio.sleep(1)

    async def enforce(self):
        now = int(time.time())
        to_pause = []
        with connect(settings.db_path) as conn:
            rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT id,username,quota_bytes,download_bytes,
                           expires_at,paused,status
                    FROM users WHERE paused=0 AND status='active'
                    """
                )
            ]
        for row in rows:
            over = row["quota_bytes"] > 0 and row["download_bytes"] >= row["quota_bytes"]
            expired = row["expires_at"] <= now
            if over or expired:
                to_pause.append(row)

        for row in to_pause:
            try:
                await asyncio.to_thread(
                    self.helper,
                    {"action": "user.pause", "username": row["username"]},
                )
            except Exception:
                pass
            with transaction(settings.db_path, immediate=True) as conn:
                conn.execute(
                    """
                    UPDATE users SET paused=1,paused_at=?,status='expired',updated_at=?
                    WHERE id=? AND paused=0
                    """,
                    (now, now, row["id"]),
                )
                self.audit(conn, "auto_pause", row["username"], "quota_or_time")
        if to_pause:
            await self.sync_backend()

    async def enforcement_loop(self):
        while True:
            try:
                await self.enforce()
            except Exception:
                pass
            await asyncio.sleep(2)

    def remaining_text(self, expires_at, paused=False, paused_at=None):
        reference = paused_at if paused and paused_at else int(time.time())
        seconds = max(0, int(expires_at) - int(reference))
        days, rem = divmod(seconds, 86400)
        hours = rem // 3600
        if days:
            return f"{days} روز و {hours} ساعت"
        return f"{hours} ساعت"

    async def stats(self):
        users = self.rows()
        async with self.lock:
            gateway_live = int(time.time()) - self.gateway_seen <= 3
            gateway = dict(self.gateway_sessions) if gateway_live else {}
            pam = {key: len(value) for key, value in self.pam_sessions.items()}
            process_counts = dict(self.process_sessions)

        result = []
        for row in users:
            username = row["username"]
            gw = gateway.get(str(row["id"]), {})
            auth_count = max(process_counts.get(username, 0), pam.get(username, 0))
            result.append({
                "id": row["id"],
                "username": username,
                "tcp_enabled": bool(row["tcp_enabled"]),
                "ws_enabled": bool(row["ws_enabled"]),
                "tcp_port": row["tcp_port"],
                "ws_token": row["ws_token"],
                "quota_bytes": row["quota_bytes"],
                "download_bytes": row["download_bytes"],
                "upload_bytes": row["upload_bytes"],
                "remaining": self.remaining_text(
                    row["expires_at"], bool(row["paused"]), row["paused_at"]
                ),
                "paused": bool(row["paused"]),
                "status": row["status"],
                "online": auth_count > 0,
                "authenticated_sessions": auth_count,
                "tcp_connections": int(gw.get("tcp", 0)),
                "ws_connections": int(gw.get("ws", 0)),
            })
        return {
            "gateway_live": gateway_live,
            "users": result,
            "total_users": len(result),
            "online_users": sum(1 for user in result if user["online"]),
            "active_users": sum(1 for user in result if not user["paused"]),
            "total_download_bytes": sum(user["download_bytes"] for user in result),
            "total_quota_bytes": sum(user["quota_bytes"] for user in result),
        }

    async def create_user(self, params):
        username = validate_username(params["username"])
        password = validate_password(params["password"])
        quota_gb = as_float(params.get("quota_gb", 0), minimum=0, maximum=100000, label="حجم")
        days = as_int(params.get("days", 30), minimum=1, maximum=3650, label="زمان")
        tcp_enabled = bool(params.get("tcp_enabled", True))
        ws_enabled = bool(params.get("ws_enabled", True))
        if not tcp_enabled and not ws_enabled:
            raise ValueError("حداقل یک روش اتصال باید فعال باشد.")

        with connect(settings.db_path) as conn:
            if conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
                raise ValueError("این نام کاربری قبلاً وجود دارد.")

        tcp_port = (
            self.allocate("tcp_port", settings.tcp_port_start, settings.tcp_port_end)
            if tcp_enabled else None
        )
        backend_port = self.allocate(
            "backend_port", settings.backend_port_start, settings.backend_port_end
        )
        ws_token = secrets.token_urlsafe(24)
        now = int(time.time())

        await asyncio.to_thread(
            self.helper,
            {"action": "user.upsert", "username": username, "password": password},
        )
        try:
            with transaction(settings.db_path, immediate=True) as conn:
                conn.execute(
                    """
                    INSERT INTO users(
                        username,password_enc,tcp_enabled,ws_enabled,tcp_port,
                        backend_port,ws_token,quota_bytes,expires_at,
                        paused,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,0,'active',?,?)
                    """,
                    (
                        username, encrypt_text(password), int(tcp_enabled), int(ws_enabled),
                        tcp_port, backend_port, ws_token, int(quota_gb * 1024**3),
                        now + days * 86400, now, now,
                    ),
                )
                self.audit(conn, "create_user", username)
        except Exception:
            await asyncio.to_thread(
                self.helper,
                {"action": "user.delete", "username": username},
            )
            raise

        await self.sync_backend()
        return {"created": True}

    async def edit_user(self, params):
        username = validate_username(params["username"])
        quota_gb = as_float(params.get("quota_gb", 0), minimum=0, maximum=100000, label="حجم")
        days = as_int(params.get("days", 30), minimum=0, maximum=3650, label="زمان")
        tcp_enabled = bool(params.get("tcp_enabled", True))
        ws_enabled = bool(params.get("ws_enabled", True))
        if not tcp_enabled and not ws_enabled:
            raise ValueError("حداقل یک روش اتصال باید فعال باشد.")

        with connect(settings.db_path) as conn:
            row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            if not row:
                raise ValueError("کاربر پیدا نشد.")
            row = dict(row)

        password = params.get("password", "")
        if password:
            password = validate_password(password)
            await asyncio.to_thread(
                self.helper,
                {"action": "user.password", "username": username, "password": password},
            )
            password_enc = encrypt_text(password)
        else:
            password_enc = row["password_enc"]

        tcp_port = row["tcp_port"]
        if tcp_enabled and tcp_port is None:
            tcp_port = self.allocate("tcp_port", settings.tcp_port_start, settings.tcp_port_end)
        if not tcp_enabled:
            tcp_port = None

        now = int(time.time())
        reference = row["paused_at"] if row["paused"] and row["paused_at"] else now
        expires_at = reference + days * 86400

        with transaction(settings.db_path, immediate=True) as conn:
            conn.execute(
                """
                UPDATE users SET password_enc=?,tcp_enabled=?,ws_enabled=?,
                    tcp_port=?,quota_bytes=?,expires_at=?,updated_at=?
                WHERE username=?
                """,
                (
                    password_enc, int(tcp_enabled), int(ws_enabled), tcp_port,
                    int(quota_gb * 1024**3), expires_at, now, username,
                ),
            )
            self.audit(conn, "edit_user", username)
        await self.sync_backend()
        return {"updated": True}

    async def pause_user(self, params):
        username = validate_username(params["username"])
        now = int(time.time())
        await asyncio.to_thread(
            self.helper, {"action": "user.pause", "username": username}
        )
        with transaction(settings.db_path, immediate=True) as conn:
            conn.execute(
                "UPDATE users SET paused=1,paused_at=?,status='paused',updated_at=? WHERE username=?",
                (now, now, username),
            )
            self.audit(conn, "pause_user", username)
        return {"paused": True}

    async def resume_user(self, params):
        username = validate_username(params["username"])
        now = int(time.time())
        with connect(settings.db_path) as conn:
            row = conn.execute(
                "SELECT expires_at,paused_at FROM users WHERE username=?", (username,)
            ).fetchone()
            if not row:
                raise ValueError("کاربر پیدا نشد.")
        shift = now - int(row["paused_at"] or now)
        await asyncio.to_thread(
            self.helper, {"action": "user.resume", "username": username}
        )
        with transaction(settings.db_path, immediate=True) as conn:
            conn.execute(
                """
                UPDATE users SET paused=0,paused_at=NULL,status='active',
                    expires_at=expires_at+?,updated_at=?
                WHERE username=?
                """,
                (max(0, shift), now, username),
            )
            self.audit(conn, "resume_user", username)
        return {"resumed": True}

    async def delete_user(self, params):
        username = validate_username(params["username"])
        await asyncio.to_thread(
            self.helper, {"action": "user.delete", "username": username}
        )
        with transaction(settings.db_path, immediate=True) as conn:
            conn.execute("DELETE FROM users WHERE username=?", (username,))
            self.audit(conn, "delete_user", username)
        await self.sync_backend()
        return {"deleted": True}

    async def reset_usage(self, params):
        username = validate_username(params["username"])
        now = int(time.time())
        with transaction(settings.db_path, immediate=True) as conn:
            conn.execute(
                """
                UPDATE users SET download_bytes=0,upload_bytes=0,
                    tcp_download_bytes=0,tcp_upload_bytes=0,
                    ws_download_bytes=0,ws_upload_bytes=0,updated_at=?
                WHERE username=?
                """,
                (now, username),
            )
            self.audit(conn, "reset_usage", username)
        return {"reset": True}

    async def user_config(self, params):
        username = validate_username(params["username"])
        with connect(settings.db_path) as conn:
            row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            if not row:
                raise ValueError("کاربر پیدا نشد.")
            row = dict(row)
        return {
            "username": username,
            "password": decrypt_text(row["password_enc"]),
            "tcp_enabled": bool(row["tcp_enabled"]),
            "tcp_port": row["tcp_port"],
            "ws_enabled": bool(row["ws_enabled"]),
            "ws_url": f"ws://{settings.server_host}:{settings.ws_port}/ws/{row['ws_token']}",
            "server": settings.server_host,
            "ws_port": settings.ws_port,
            "ws_path": f"/ws/{row['ws_token']}",
        }

    async def change_admin(self, params):
        username = validate_username(params["username"])
        password = params["password"]
        if len(password) < 10:
            raise ValueError("رمز مدیر باید حداقل ۱۰ کاراکتر باشد.")
        now = int(time.time())
        await asyncio.to_thread(
            self.helper,
            {
                "action": "admin.credentials",
                "username": username,
                "password": password,
            },
        )
        with transaction(settings.db_path, immediate=True) as conn:
            conn.execute(
                """
                INSERT INTO admins(id,username,password_hash,session_version,updated_at)
                VALUES(1,?,?,1,?)
                ON CONFLICT(id) DO UPDATE SET
                    username=excluded.username,
                    password_hash=excluded.password_hash,
                    session_version=admins.session_version+1,
                    updated_at=excluded.updated_at
                """,
                (username, generate_password_hash(password), now),
            )
            self.audit(conn, "change_admin", username)
        return {"changed": True}

    async def backup_export(self):
        result = []
        with connect(settings.db_path) as conn:
            rows = [dict(row) for row in conn.execute("SELECT * FROM users ORDER BY id")]
        for row in rows:
            row["password"] = decrypt_text(row.pop("password_enc"))
            result.append(row)
        return {"version": 1, "created_at": int(time.time()), "users": result}

    async def backup_restore(self, params):
        payload = params["backup"]
        if not isinstance(payload.get("users"), list):
            raise ValueError("ساختار بکاپ معتبر نیست.")

        current = self.rows()
        for row in current:
            try:
                await asyncio.to_thread(
                    self.helper, {"action": "user.delete", "username": row["username"]}
                )
            except Exception:
                pass

        with transaction(settings.db_path, immediate=True) as conn:
            conn.execute("DELETE FROM users")

        for item in payload["users"]:
            username = validate_username(item["username"])
            password = validate_password(item["password"])
            await asyncio.to_thread(
                self.helper,
                {"action": "user.upsert", "username": username, "password": password},
            )
            with transaction(settings.db_path, immediate=True) as conn:
                conn.execute(
                    """
                    INSERT INTO users(
                        username,password_enc,tcp_enabled,ws_enabled,tcp_port,
                        backend_port,ws_token,quota_bytes,download_bytes,upload_bytes,
                        tcp_download_bytes,tcp_upload_bytes,ws_download_bytes,ws_upload_bytes,
                        expires_at,paused,paused_at,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        username, encrypt_text(password), int(item.get("tcp_enabled", 1)),
                        int(item.get("ws_enabled", 1)), item.get("tcp_port"),
                        int(item["backend_port"]), item.get("ws_token") or secrets.token_urlsafe(24),
                        int(item.get("quota_bytes", 0)), int(item.get("download_bytes", 0)),
                        int(item.get("upload_bytes", 0)), int(item.get("tcp_download_bytes", 0)),
                        int(item.get("tcp_upload_bytes", 0)), int(item.get("ws_download_bytes", 0)),
                        int(item.get("ws_upload_bytes", 0)), int(item["expires_at"]),
                        int(item.get("paused", 0)), item.get("paused_at"),
                        item.get("status", "active"), int(item.get("created_at", time.time())),
                        int(time.time()),
                    ),
                )
        await self.sync_backend()
        return {"restored": True}

    async def dispatch(self, method, params):
        if method == "health":
            return {"status": "ok", "gateway_seen": self.gateway_seen}
        if method == "gateway.config":
            return self.active_config()
        if method == "gateway.metrics":
            return await self.gateway_metrics(params)
        if method == "pam.event":
            return await self.pam_event(params)
        if method == "stats":
            return await self.stats()
        if method == "user.create":
            return await self.create_user(params)
        if method == "user.edit":
            return await self.edit_user(params)
        if method == "user.pause":
            return await self.pause_user(params)
        if method == "user.resume":
            return await self.resume_user(params)
        if method == "user.delete":
            return await self.delete_user(params)
        if method == "user.reset_usage":
            return await self.reset_usage(params)
        if method == "user.config":
            return await self.user_config(params)
        if method == "admin.change":
            return await self.change_admin(params)
        if method == "backup.export":
            return await self.backup_export()
        if method == "backup.restore":
            return await self.backup_restore(params)
        raise ValueError("Unknown manager method")

    async def handle(self, reader, writer):
        try:
            raw = await reader.readline()
            payload = json.loads(raw.decode())
            result = await self.dispatch(payload.get("method", ""), payload.get("params", {}))
            response = {"ok": True, "result": result}
        except Exception as exc:
            response = {"ok": False, "error": str(exc)}
        writer.write((json.dumps(response, separators=(",", ":")) + "\n").encode())
        await writer.drain()
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

    async def run(self):
        socket_path = Path(settings.manager_socket)
        socket_path.parent.mkdir(parents=True, exist_ok=True)
        socket_path.unlink(missing_ok=True)
        server = await asyncio.start_unix_server(self.handle, path=str(socket_path))
        os.chmod(socket_path, 0o660)
        await self.sync_backend()
        async with server:
            await asyncio.gather(
                server.serve_forever(),
                self.reconcile_sessions(),
                self.drain_pam_spool(),
                self.enforcement_loop(),
            )

async def main():
    manager = Manager()
    await manager.run()

if __name__ == "__main__":
    asyncio.run(main())
