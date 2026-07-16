import asyncio
import ssl
import time
from dataclasses import dataclass

import websockets

from .config import Config
from .db import connect, init_db

@dataclass(frozen=True)
class Endpoint:
    user_id: int
    transport: str
    port: int
    backend_port: int
    token: str | None = None

class Counters:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.data = {}

    async def change(self, user_id, transport, rx=0, tx=0, online_delta=0):
        async with self.lock:
            key = (user_id, transport)
            item = self.data.setdefault(key, {"rx": 0, "tx": 0, "online": 0})
            item["rx"] += rx
            item["tx"] += tx
            item["online"] = max(0, item["online"] + online_delta)

    async def flush(self):
        async with self.lock:
            snapshot = {
                key: dict(value)
                for key, value in self.data.items()
            }
            for value in self.data.values():
                value["rx"] = 0
                value["tx"] = 0

        now = int(time.time())
        with connect() as c:
            for (uid, transport), item in snapshot.items():
                c.execute("""
                INSERT INTO transport_usage(user_id,transport,rx_bytes,tx_bytes,online,last_seen)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(user_id,transport) DO UPDATE SET
                  rx_bytes=transport_usage.rx_bytes+excluded.rx_bytes,
                  tx_bytes=transport_usage.tx_bytes+excluded.tx_bytes,
                  online=excluded.online,
                  last_seen=CASE WHEN excluded.online>0 THEN excluded.last_seen ELSE transport_usage.last_seen END
                """, (uid,transport,item["rx"],item["tx"],item["online"],now))

            c.execute("""
            UPDATE users SET
              rx_bytes=COALESCE((SELECT SUM(rx_bytes) FROM transport_usage t WHERE t.user_id=users.id),0),
              tx_bytes=COALESCE((SELECT SUM(tx_bytes) FROM transport_usage t WHERE t.user_id=users.id),0),
              online_count=COALESCE((SELECT SUM(online) FROM transport_usage t WHERE t.user_id=users.id),0),
              last_seen=COALESCE((SELECT MAX(last_seen) FROM transport_usage t WHERE t.user_id=users.id),0),
              updated_at=CURRENT_TIMESTAMP
            """)
            c.commit()

COUNTERS = Counters()

def endpoints():
    with connect() as c:
        users = [dict(r) for r in c.execute(
            "SELECT * FROM users WHERE paused=0 AND status='Active'"
        )]
    result = []
    for u in users:
        if u["openssh_enabled"] and u["openssh_port"]:
            result.append(Endpoint(u["id"], "openssh", u["openssh_port"], 2222))
        if u["dropbear_enabled"] and u["dropbear_port"]:
            result.append(Endpoint(u["id"], "dropbear", u["dropbear_port"], 2223))
        if u["ws_enabled"] and u["ws_port"]:
            result.append(Endpoint(u["id"], "ws", u["ws_port"], 2222, u["ws_token"]))
        if u["tls_enabled"] and u["tls_port"]:
            result.append(Endpoint(u["id"], "tls", u["tls_port"], 2222))
    return result

async def tcp_pipe(reader, writer, ep, direction):
    try:
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                return
            writer.write(chunk)
            await writer.drain()
            if direction == "rx":
                await COUNTERS.change(ep.user_id, ep.transport, rx=len(chunk))
            else:
                await COUNTERS.change(ep.user_id, ep.transport, tx=len(chunk))
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

async def tcp_connection(client_r, client_w, ep):
    await COUNTERS.change(ep.user_id, ep.transport, online_delta=1)
    try:
        server_r, server_w = await asyncio.open_connection("127.0.0.1", ep.backend_port)
        await asyncio.gather(
            tcp_pipe(client_r, server_w, ep, "rx"),
            tcp_pipe(server_r, client_w, ep, "tx"),
        )
    finally:
        await COUNTERS.change(ep.user_id, ep.transport, online_delta=-1)

async def ws_connection(ws, ep):
    if ws.request.path != f"/ws/{ep.token}":
        await ws.close(code=1008, reason="invalid path")
        return

    await COUNTERS.change(ep.user_id, ep.transport, online_delta=1)
    server_w = None
    try:
        server_r, server_w = await asyncio.open_connection("127.0.0.1", ep.backend_port)

        async def ws_to_tcp():
            async for message in ws:
                if isinstance(message, str):
                    message = message.encode()
                server_w.write(message)
                await server_w.drain()
                await COUNTERS.change(ep.user_id, ep.transport, rx=len(message))

        async def tcp_to_ws():
            while True:
                chunk = await server_r.read(65536)
                if not chunk:
                    return
                await ws.send(chunk)
                await COUNTERS.change(ep.user_id, ep.transport, tx=len(chunk))

        await asyncio.gather(ws_to_tcp(), tcp_to_ws())
    finally:
        await COUNTERS.change(ep.user_id, ep.transport, online_delta=-1)
        if server_w:
            server_w.close()
            await server_w.wait_closed()

async def flush_loop():
    while True:
        await asyncio.sleep(5)
        await COUNTERS.flush()

async def main():
    init_db(Config.DB_PATH)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(Config.TLS_CERT, Config.TLS_KEY)

    servers = []
    for ep in endpoints():
        if ep.transport == "ws":
            servers.append(await websockets.serve(
                lambda ws, endpoint=ep: ws_connection(ws, endpoint),
                "0.0.0.0", ep.port, max_size=None,
                ping_interval=25, ping_timeout=20,
            ))
        else:
            servers.append(await asyncio.start_server(
                lambda r,w,endpoint=ep: tcp_connection(r,w,endpoint),
                "0.0.0.0", ep.port,
                ssl=tls if ep.transport == "tls" else None,
            ))

    await flush_loop()

if __name__ == "__main__":
    asyncio.run(main())
