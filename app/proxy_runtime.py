import asyncio
import signal
import time
from dataclasses import dataclass

from .config import Config
from .db import connect, init_db

@dataclass(frozen=True)
class Endpoint:
    user_id: int
    port: int

class ProxyRuntime:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.counters = {}
        self.servers = []
        self.stop = asyncio.Event()

    def endpoints(self):
        with connect() as conn:
            rows = conn.execute("""
            SELECT id,port FROM users
            WHERE paused=0 AND status='Active' AND remaining_days>0
            """).fetchall()
        return [Endpoint(int(row["id"]), int(row["port"])) for row in rows]

    async def update(self, uid, rx=0, tx=0, online_delta=0):
        async with self.lock:
            item = self.counters.setdefault(uid, {"rx": 0, "tx": 0, "online": 0})
            item["rx"] += rx
            item["tx"] += tx
            item["online"] = max(0, item["online"] + online_delta)

    async def relay(self, reader, writer, endpoint, direction):
        try:
            while True:
                data = await reader.read(131072)
                if not data:
                    return
                writer.write(data)
                await writer.drain()
                if direction == "rx":
                    await self.update(endpoint.user_id, rx=len(data))
                else:
                    await self.update(endpoint.user_id, tx=len(data))
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def connection(self, client_reader, client_writer, endpoint):
        await self.update(endpoint.user_id, online_delta=1)
        try:
            server_reader, server_writer = await asyncio.open_connection(
                "127.0.0.1", Config.INTERNAL_SSH_PORT
            )
            await asyncio.gather(
                self.relay(client_reader, server_writer, endpoint, "rx"),
                self.relay(server_reader, client_writer, endpoint, "tx"),
            )
        except Exception:
            try:
                client_writer.close()
                await client_writer.wait_closed()
            except Exception:
                pass
        finally:
            await self.update(endpoint.user_id, online_delta=-1)

    async def flush(self):
        async with self.lock:
            snapshot = {uid: dict(values) for uid, values in self.counters.items()}
            for values in self.counters.values():
                values["rx"] = 0
                values["tx"] = 0
        if not snapshot:
            return

        now = int(time.time())
        with connect() as conn:
            conn.executemany("""
            UPDATE users
            SET rx_bytes=rx_bytes+?,
                tx_bytes=tx_bytes+?,
                online=?,
                last_seen=CASE WHEN ?>0 THEN ? ELSE last_seen END,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """, [
                (
                    values["rx"], values["tx"], values["online"],
                    values["online"], now, uid,
                )
                for uid, values in snapshot.items()
            ])
            conn.commit()

    async def flush_loop(self):
        while not self.stop.is_set():
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=3)
            except asyncio.TimeoutError:
                await self.flush()
        await self.flush()

    async def run(self):
        for endpoint in self.endpoints():
            server = await asyncio.start_server(
                lambda r, w, ep=endpoint: self.connection(r, w, ep),
                "0.0.0.0",
                endpoint.port,
                backlog=256,
                reuse_address=True,
            )
            self.servers.append(server)

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self.stop.set)

        await self.flush_loop()
        for server in self.servers:
            server.close()
            await server.wait_closed()

async def main():
    init_db(Config.DB_PATH)
    await ProxyRuntime().run()

if __name__ == "__main__":
    asyncio.run(main())
