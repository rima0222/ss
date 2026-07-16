import asyncio
import json
import os
import signal
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import websockets

from .config import Config
from .db import connect, init_db

@dataclass(frozen=True)
class Endpoint:
    user_id: int
    username: str
    kind: str
    port: int
    token: str | None = None

class Gateway:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.sessions = {}
        self.totals = {}
        self.tcp_servers = {}
        self.ws_servers = {}
        self.stop = asyncio.Event()
        self.live_path = Path(Config.LIVE_PATH)

    def load_endpoints(self):
        with connect() as conn:
            users = [dict(row) for row in conn.execute("""
            SELECT id,username,tcp_enabled,ws_enabled,tcp_port,ws_port,ws_token
            FROM users
            WHERE paused=0 AND status='Active' AND remaining_days>0
            """)]

        tcp, ws = {}, {}
        for user in users:
            if user["tcp_enabled"] and user["tcp_port"]:
                ep = Endpoint(
                    int(user["id"]), user["username"], "tcp", int(user["tcp_port"])
                )
                tcp[ep.port] = ep
                self.totals.setdefault((ep.user_id, ep.kind), {
                    "user_id": ep.user_id,
                    "username": ep.username,
                    "kind": ep.kind,
                    "pending_rx": 0,
                    "pending_tx": 0,
                    "last_seen": 0,
                })

            if user["ws_enabled"] and user["ws_port"]:
                ep = Endpoint(
                    int(user["id"]), user["username"], "ws",
                    int(user["ws_port"]), user["ws_token"]
                )
                ws[ep.port] = ep
                self.totals.setdefault((ep.user_id, ep.kind), {
                    "user_id": ep.user_id,
                    "username": ep.username,
                    "kind": ep.kind,
                    "pending_rx": 0,
                    "pending_tx": 0,
                    "last_seen": 0,
                })
        return tcp, ws

    async def open_session(self, endpoint):
        session_id = uuid.uuid4().hex
        now = int(time.time())
        async with self.lock:
            self.sessions[session_id] = {
                "id": session_id,
                "user_id": endpoint.user_id,
                "username": endpoint.username,
                "kind": endpoint.kind,
                "started_at": now,
                "last_activity": now,
                "rx": 0,
                "tx": 0,
            }
        return session_id

    async def add_bytes(self, session_id, endpoint, rx=0, tx=0):
        now = int(time.time())
        async with self.lock:
            session = self.sessions.get(session_id)
            if session:
                session["rx"] += rx
                session["tx"] += tx
                session["last_activity"] = now

            total = self.totals.setdefault((endpoint.user_id, endpoint.kind), {
                "user_id": endpoint.user_id,
                "username": endpoint.username,
                "kind": endpoint.kind,
                "pending_rx": 0,
                "pending_tx": 0,
                "last_seen": 0,
            })
            total["pending_rx"] += rx
            total["pending_tx"] += tx
            total["last_seen"] = now

    async def close_session(self, session_id):
        async with self.lock:
            self.sessions.pop(session_id, None)

    async def relay(self, reader, writer, endpoint, session_id, direction):
        try:
            while True:
                data = await reader.read(131072)
                if not data:
                    return
                writer.write(data)
                await writer.drain()
                if direction == "rx":
                    await self.add_bytes(session_id, endpoint, rx=len(data))
                else:
                    await self.add_bytes(session_id, endpoint, tx=len(data))
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def handle_tcp(self, client_reader, client_writer, endpoint):
        session_id = await self.open_session(endpoint)
        try:
            backend_reader, backend_writer = await asyncio.open_connection(
                "127.0.0.1", Config.INTERNAL_SSH_PORT
            )
            await asyncio.gather(
                self.relay(client_reader, backend_writer, endpoint, session_id, "rx"),
                self.relay(backend_reader, client_writer, endpoint, session_id, "tx"),
            )
        except Exception:
            try:
                client_writer.close()
                await client_writer.wait_closed()
            except Exception:
                pass
        finally:
            await self.close_session(session_id)

    async def handle_ws(self, websocket, endpoint):
        if websocket.request.path != f"/ws/{endpoint.token}":
            await websocket.close(code=1008, reason="invalid path")
            return

        session_id = await self.open_session(endpoint)
        backend_writer = None
        try:
            backend_reader, backend_writer = await asyncio.open_connection(
                "127.0.0.1", Config.INTERNAL_SSH_PORT
            )

            async def ws_to_ssh():
                async for message in websocket:
                    if isinstance(message, str):
                        message = message.encode()
                    backend_writer.write(message)
                    await backend_writer.drain()
                    await self.add_bytes(session_id, endpoint, rx=len(message))

            async def ssh_to_ws():
                while True:
                    data = await backend_reader.read(131072)
                    if not data:
                        return
                    await websocket.send(data)
                    await self.add_bytes(session_id, endpoint, tx=len(data))

            await asyncio.gather(ws_to_ssh(), ssh_to_ws())
        finally:
            await self.close_session(session_id)
            if backend_writer:
                backend_writer.close()
                try:
                    await backend_writer.wait_closed()
                except Exception:
                    pass

    async def reconcile(self):
        wanted_tcp, wanted_ws = self.load_endpoints()

        for port in set(self.tcp_servers) - set(wanted_tcp):
            server = self.tcp_servers.pop(port)
            server.close()
            await server.wait_closed()

        for port in set(self.ws_servers) - set(wanted_ws):
            server = self.ws_servers.pop(port)
            server.close()
            await server.wait_closed()

        for port in set(wanted_tcp) - set(self.tcp_servers):
            endpoint = wanted_tcp[port]
            self.tcp_servers[port] = await asyncio.start_server(
                lambda r, w, ep=endpoint: self.handle_tcp(r, w, ep),
                "0.0.0.0",
                endpoint.port,
                backlog=512,
                reuse_address=True,
            )

        for port in set(wanted_ws) - set(self.ws_servers):
            endpoint = wanted_ws[port]
            self.ws_servers[port] = await websockets.serve(
                lambda ws, ep=endpoint: self.handle_ws(ws, ep),
                "0.0.0.0",
                endpoint.port,
                max_size=None,
                ping_interval=20,
                ping_timeout=15,
                compression=None,
                max_queue=32,
                write_limit=131072,
            )

    async def reconcile_loop(self):
        while not self.stop.is_set():
            try:
                await self.reconcile()
            except Exception:
                pass
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass

    async def write_live_snapshot(self):
        async with self.lock:
            sessions = [dict(value) for value in self.sessions.values()]
            totals = [dict(value) for value in self.totals.values()]

        users = {}
        for total in totals:
            user = users.setdefault(total["username"], {
                "online_tcp": 0,
                "online_ws": 0,
                "pending_rx": 0,
                "pending_tx": 0,
                "last_seen": 0,
            })
            user["pending_rx"] += int(total["pending_rx"])
            user["pending_tx"] += int(total["pending_tx"])
            user["last_seen"] = max(user["last_seen"], int(total["last_seen"]))

        for session in sessions:
            user = users.setdefault(session["username"], {
                "online_tcp": 0,
                "online_ws": 0,
                "pending_rx": 0,
                "pending_tx": 0,
                "last_seen": 0,
            })
            user[f"online_{session['kind']}"] += 1
            user["last_seen"] = max(user["last_seen"], int(session["last_activity"]))

        payload = {
            "updated_at": int(time.time()),
            "session_count": len(sessions),
            "users": users,
        }

        self.live_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.live_path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(payload, separators=(",", ":")),
            encoding="utf-8",
        )
        os.chmod(temp_path, 0o660)
        os.replace(temp_path, self.live_path)

    async def snapshot_loop(self):
        while not self.stop.is_set():
            try:
                await self.write_live_snapshot()
            except Exception:
                pass
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                pass

    async def take_pending(self):
        async with self.lock:
            pending = []
            for key, value in self.totals.items():
                rx = int(value["pending_rx"])
                tx = int(value["pending_tx"])
                if rx or tx:
                    pending.append((
                        key,
                        value["user_id"],
                        value["kind"],
                        rx,
                        tx,
                        int(value["last_seen"]),
                    ))
                    value["pending_rx"] = 0
                    value["pending_tx"] = 0
            return pending

    async def restore_pending(self, pending):
        async with self.lock:
            for key, _uid, _kind, rx, tx, _last_seen in pending:
                item = self.totals.get(key)
                if item:
                    item["pending_rx"] += rx
                    item["pending_tx"] += tx

    async def persist(self):
        pending = await self.take_pending()
        if not pending:
            return

        for attempt in range(6):
            try:
                with connect() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    for _key, user_id, kind, rx, tx, last_seen in pending:
                        conn.execute("""
                        INSERT INTO endpoint_usage(
                          user_id,endpoint,rx_bytes,tx_bytes,online,last_seen
                        ) VALUES(?,?,?,?,0,?)
                        ON CONFLICT(user_id,endpoint) DO UPDATE SET
                          rx_bytes=endpoint_usage.rx_bytes+excluded.rx_bytes,
                          tx_bytes=endpoint_usage.tx_bytes+excluded.tx_bytes,
                          last_seen=MAX(endpoint_usage.last_seen,excluded.last_seen)
                        """, (user_id, kind, rx, tx, last_seen))

                    conn.execute("""
                    UPDATE users SET
                      rx_bytes=COALESCE((
                        SELECT SUM(rx_bytes)
                        FROM endpoint_usage e
                        WHERE e.user_id=users.id
                      ),0),
                      tx_bytes=COALESCE((
                        SELECT SUM(tx_bytes)
                        FROM endpoint_usage e
                        WHERE e.user_id=users.id
                      ),0),
                      last_seen=COALESCE((
                        SELECT MAX(last_seen)
                        FROM endpoint_usage e
                        WHERE e.user_id=users.id
                      ),0),
                      updated_at=CURRENT_TIMESTAMP
                    """)
                    conn.commit()
                return
            except sqlite3.OperationalError:
                await asyncio.sleep(0.2 * (attempt + 1))
            except Exception:
                await asyncio.sleep(0.2 * (attempt + 1))

        await self.restore_pending(pending)

    async def persistence_loop(self):
        while not self.stop.is_set():
            try:
                await self.persist()
            except Exception:
                pass
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=3)
            except asyncio.TimeoutError:
                pass
        await self.persist()

    async def initialize(self):
        with connect() as conn:
            conn.execute("UPDATE users SET online_tcp=0,online_ws=0")
            conn.execute("UPDATE endpoint_usage SET online=0")
            conn.commit()
        self.live_path.unlink(missing_ok=True)

    async def run(self):
        await self.initialize()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self.stop.set)

        await self.reconcile()
        await asyncio.gather(
            self.reconcile_loop(),
            self.snapshot_loop(),
            self.persistence_loop(),
        )

async def main():
    init_db(Config.DB_PATH)
    await Gateway().run()

if __name__ == "__main__":
    asyncio.run(main())
