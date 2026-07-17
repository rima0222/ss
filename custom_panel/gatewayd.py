import asyncio
import json
import socket
import time
import uuid
from collections import defaultdict

from websockets.asyncio.server import serve

from .ipc import async_request
from .settings import settings

class Gateway:
    def __init__(self):
        self.config = {}
        self.tcp_servers = {}
        self.ws_server = None
        self.sessions = {}
        self.deltas = defaultdict(lambda: {"download": 0, "upload": 0})
        self.lock = asyncio.Lock()
        self.stop = asyncio.Event()

    def tune_writer(self, writer):
        sock = writer.get_extra_info("socket")
        if sock:
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            except OSError:
                pass

    async def add_session(self, user, kind, closer):
        session_id = uuid.uuid4().hex
        async with self.lock:
            self.sessions[session_id] = {
                "user_id": int(user["id"]),
                "kind": kind,
                "closer": closer,
                "started": time.monotonic(),
            }
        return session_id

    async def remove_session(self, session_id):
        async with self.lock:
            self.sessions.pop(session_id, None)

    async def count(self, user_id, kind, download=0, upload=0):
        async with self.lock:
            key = (int(user_id), kind)
            self.deltas[key]["download"] += int(download)
            self.deltas[key]["upload"] += int(upload)

    async def tcp_pipe(self, reader, writer, user, session_id, direction):
        try:
            while True:
                data = await reader.read(131072)
                if not data:
                    return
                writer.write(data)
                await writer.drain()
                if direction == "download":
                    await self.count(user["id"], "tcp", download=len(data))
                else:
                    await self.count(user["id"], "tcp", upload=len(data))
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def handle_tcp(self, client_reader, client_writer, user):
        self.tune_writer(client_writer)
        backend_writer = None
        session_id = await self.add_session(
            user, "tcp", lambda: client_writer.close()
        )
        try:
            backend_reader, backend_writer = await asyncio.open_connection(
                "127.0.0.1", int(user["backend_port"])
            )
            self.tune_writer(backend_writer)
            await asyncio.gather(
                self.tcp_pipe(client_reader, backend_writer, user, session_id, "upload"),
                self.tcp_pipe(backend_reader, client_writer, user, session_id, "download"),
            )
        except Exception:
            client_writer.close()
        finally:
            if backend_writer:
                backend_writer.close()
            await self.remove_session(session_id)

    async def handle_ws(self, connection):
        path = connection.request.path
        token = path.removeprefix("/ws/") if path.startswith("/ws/") else ""
        users = {
            user["ws_token"]: user
            for user in self.config.get("users", [])
            if user.get("ws_enabled")
        }
        user = users.get(token)
        if not user:
            await connection.close(code=1008, reason="invalid token")
            return

        backend_writer = None
        session_id = await self.add_session(
            user, "ws", lambda: asyncio.create_task(connection.close())
        )
        try:
            backend_reader, backend_writer = await asyncio.open_connection(
                "127.0.0.1", int(user["backend_port"])
            )
            self.tune_writer(backend_writer)

            async def client_to_backend():
                async for message in connection:
                    if isinstance(message, str):
                        message = message.encode()
                    backend_writer.write(message)
                    await backend_writer.drain()
                    await self.count(user["id"], "ws", upload=len(message))

            async def backend_to_client():
                while True:
                    data = await backend_reader.read(131072)
                    if not data:
                        return
                    await connection.send(data)
                    await self.count(user["id"], "ws", download=len(data))

            await asyncio.gather(client_to_backend(), backend_to_client())
        finally:
            if backend_writer:
                backend_writer.close()
                try:
                    await backend_writer.wait_closed()
                except Exception:
                    pass
            await self.remove_session(session_id)

    async def close_disabled_sessions(self, allowed_ids):
        closers = []
        async with self.lock:
            for session in self.sessions.values():
                if session["user_id"] not in allowed_ids:
                    closers.append(session["closer"])
        for closer in closers:
            try:
                closer()
            except Exception:
                pass

    async def reconcile(self):
        config = await async_request(
            settings.manager_socket, {"method": "gateway.config", "params": {}}, timeout=5
        )
        self.config = config
        users = config.get("users", [])
        tcp_users = {
            int(user["tcp_port"]): user
            for user in users
            if user.get("tcp_enabled") and user.get("tcp_port")
        }

        for port in set(self.tcp_servers) - set(tcp_users):
            server = self.tcp_servers.pop(port)
            server.close()
            await server.wait_closed()

        for port in set(tcp_users) - set(self.tcp_servers):
            user = tcp_users[port]
            self.tcp_servers[port] = await asyncio.start_server(
                lambda r, w, selected=user: self.handle_tcp(r, w, selected),
                "0.0.0.0",
                port,
                backlog=512,
                reuse_address=True,
            )

        allowed_ids = {int(user["id"]) for user in users}
        await self.close_disabled_sessions(allowed_ids)

        if self.ws_server is None:
            self.ws_server = await serve(
                self.handle_ws,
                "0.0.0.0",
                settings.ws_port,
                compression=None,
                ping_interval=20,
                ping_timeout=15,
                max_size=None,
                max_queue=32,
                write_limit=262144,
            )

    async def config_loop(self):
        while not self.stop.is_set():
            try:
                await self.reconcile()
            except Exception:
                pass
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=1)
            except asyncio.TimeoutError:
                pass

    async def metrics_payload(self):
        async with self.lock:
            deltas = [
                {
                    "user_id": user_id,
                    "kind": kind,
                    "download": values["download"],
                    "upload": values["upload"],
                }
                for (user_id, kind), values in self.deltas.items()
                if values["download"] or values["upload"]
            ]
            sessions = defaultdict(lambda: {"tcp": 0, "ws": 0})
            for session in self.sessions.values():
                sessions[str(session["user_id"])][session["kind"]] += 1
            return deltas, dict(sessions)

    async def acknowledge(self, sent_deltas):
        async with self.lock:
            for item in sent_deltas:
                key = (int(item["user_id"]), item["kind"])
                values = self.deltas[key]
                values["download"] = max(0, values["download"] - int(item["download"]))
                values["upload"] = max(0, values["upload"] - int(item["upload"]))

    async def metrics_loop(self):
        while not self.stop.is_set():
            try:
                deltas, sessions = await self.metrics_payload()
                await async_request(
                    settings.manager_socket,
                    {
                        "method": "gateway.metrics",
                        "params": {"deltas": deltas, "sessions": sessions},
                    },
                    timeout=10,
                )
                await self.acknowledge(deltas)
            except Exception:
                pass
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=1)
            except asyncio.TimeoutError:
                pass

    async def run(self):
        await asyncio.gather(self.config_loop(), self.metrics_loop())

async def main():
    await Gateway().run()

if __name__ == "__main__":
    asyncio.run(main())
