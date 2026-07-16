import asyncio
import signal
import time
from dataclasses import dataclass

import websockets

from .config import Config
from .db import connect, init_db

@dataclass(frozen=True)
class Endpoint:
    user_id: int
    kind: str
    port: int
    token: str | None = None

class Runtime:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.counters = {}
        self.tcp_servers = {}
        self.ws_servers = {}
        self.stop = asyncio.Event()

    def desired(self):
        with connect() as conn:
            users = [dict(row) for row in conn.execute("""
            SELECT * FROM users
            WHERE paused=0 AND status='Active' AND remaining_days>0
            """)]
        tcp = {}
        ws = {}
        for user in users:
            if user["tcp_enabled"] and user["tcp_port"]:
                tcp[int(user["tcp_port"])] = Endpoint(user["id"], "tcp", int(user["tcp_port"]))
            if user["ws_enabled"] and user["ws_port"]:
                ws[int(user["ws_port"])] = Endpoint(
                    user["id"], "ws", int(user["ws_port"]), user["ws_token"]
                )
        return tcp, ws

    async def change(self, uid, kind, rx=0, tx=0, online_delta=0):
        async with self.lock:
            key = (uid, kind)
            item = self.counters.setdefault(key, {"rx": 0, "tx": 0, "online": 0})
            item["rx"] += rx
            item["tx"] += tx
            item["online"] = max(0, item["online"] + online_delta)

    async def tcp_pipe(self, reader, writer, endpoint, direction):
        try:
            while True:
                data = await reader.read(131072)
                if not data:
                    return
                writer.write(data)
                await writer.drain()
                if direction == "rx":
                    await self.change(endpoint.user_id, endpoint.kind, rx=len(data))
                else:
                    await self.change(endpoint.user_id, endpoint.kind, tx=len(data))
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def tcp_connection(self, client_reader, client_writer, endpoint):
        await self.change(endpoint.user_id, "tcp", online_delta=1)
        try:
            server_reader, server_writer = await asyncio.open_connection(
                "127.0.0.1", Config.INTERNAL_SSH_PORT
            )
            await asyncio.gather(
                self.tcp_pipe(client_reader, server_writer, endpoint, "rx"),
                self.tcp_pipe(server_reader, client_writer, endpoint, "tx"),
            )
        except Exception:
            try:
                client_writer.close()
                await client_writer.wait_closed()
            except Exception:
                pass
        finally:
            await self.change(endpoint.user_id, "tcp", online_delta=-1)

    async def ws_connection(self, websocket, endpoint):
        if websocket.request.path != f"/ws/{endpoint.token}":
            await websocket.close(code=1008, reason="invalid path")
            return

        await self.change(endpoint.user_id, "ws", online_delta=1)
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
                    await self.change(endpoint.user_id, "ws", rx=len(message))

            async def ssh_to_ws():
                while True:
                    data = await backend_reader.read(131072)
                    if not data:
                        return
                    await websocket.send(data)
                    await self.change(endpoint.user_id, "ws", tx=len(data))

            await asyncio.gather(ws_to_ssh(), ssh_to_ws())
        finally:
            await self.change(endpoint.user_id, "ws", online_delta=-1)
            if backend_writer:
                backend_writer.close()
                await backend_writer.wait_closed()

    async def open_tcp(self, endpoint):
        return await asyncio.start_server(
            lambda r, w, ep=endpoint: self.tcp_connection(r, w, ep),
            "0.0.0.0", endpoint.port,
            backlog=256, reuse_address=True,
        )

    async def open_ws(self, endpoint):
        return await websockets.serve(
            lambda ws, ep=endpoint: self.ws_connection(ws, ep),
            "0.0.0.0", endpoint.port,
            max_size=None,
            ping_interval=25,
            ping_timeout=20,
        )

    async def reconcile(self):
        wanted_tcp, wanted_ws = self.desired()

        for port in set(self.tcp_servers) - set(wanted_tcp):
            server = self.tcp_servers.pop(port)
            server.close()
            await server.wait_closed()
        for port in set(self.ws_servers) - set(wanted_ws):
            server = self.ws_servers.pop(port)
            server.close()
            await server.wait_closed()

        for port in set(wanted_tcp) - set(self.tcp_servers):
            self.tcp_servers[port] = await self.open_tcp(wanted_tcp[port])
        for port in set(wanted_ws) - set(self.ws_servers):
            self.ws_servers[port] = await self.open_ws(wanted_ws[port])

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

    async def flush(self):
        async with self.lock:
            snapshot = {key: dict(value) for key, value in self.counters.items()}
            for value in self.counters.values():
                value["rx"] = 0
                value["tx"] = 0

        if not snapshot:
            return

        now = int(time.time())
        with connect() as conn:
            for (uid, kind), value in snapshot.items():
                conn.execute("""
                INSERT INTO endpoint_usage(user_id,endpoint,rx_bytes,tx_bytes,online,last_seen)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(user_id,endpoint) DO UPDATE SET
                  rx_bytes=endpoint_usage.rx_bytes+excluded.rx_bytes,
                  tx_bytes=endpoint_usage.tx_bytes+excluded.tx_bytes,
                  online=excluded.online,
                  last_seen=CASE WHEN excluded.online>0 THEN excluded.last_seen ELSE endpoint_usage.last_seen END
                """, (uid, kind, value["rx"], value["tx"], value["online"], now))

            conn.execute("""
            UPDATE users SET
              rx_bytes=COALESCE((SELECT SUM(rx_bytes) FROM endpoint_usage e WHERE e.user_id=users.id),0),
              tx_bytes=COALESCE((SELECT SUM(tx_bytes) FROM endpoint_usage e WHERE e.user_id=users.id),0),
              online_tcp=COALESCE((SELECT online FROM endpoint_usage e WHERE e.user_id=users.id AND e.endpoint='tcp'),0),
              online_ws=COALESCE((SELECT online FROM endpoint_usage e WHERE e.user_id=users.id AND e.endpoint='ws'),0),
              last_seen=COALESCE((SELECT MAX(last_seen) FROM endpoint_usage e WHERE e.user_id=users.id),0),
              updated_at=CURRENT_TIMESTAMP
            """)
            conn.commit()

    async def flush_loop(self):
        while not self.stop.is_set():
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=3)
            except asyncio.TimeoutError:
                await self.flush()
        await self.flush()

    async def run(self):
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self.stop.set)
        await self.reconcile()
        await asyncio.gather(self.reconcile_loop(), self.flush_loop())

async def main():
    init_db(Config.DB_PATH)
    await Runtime().run()

if __name__ == "__main__":
    asyncio.run(main())
