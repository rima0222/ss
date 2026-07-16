import asyncio
import json
import os
import signal
import ssl
import time
from dataclasses import dataclass
from pathlib import Path

import websockets

from .config import Config
from .db import connect, init_db

@dataclass
class Endpoint:
    user_id: int
    username: str
    transport: str
    port: int
    token: str | None
    backend_port: int

class CounterBuffer:
    def __init__(self):
        self.data = {}
        self.lock = asyncio.Lock()

    async def add(self, user_id, transport, rx=0, tx=0, online_delta=0):
        async with self.lock:
            key = (user_id, transport)
            item = self.data.setdefault(key, {"rx": 0, "tx": 0, "online": 0})
            item["rx"] += rx
            item["tx"] += tx
            item["online"] = max(0, item["online"] + online_delta)

    async def flush(self):
        async with self.lock:
            snapshot = self.data
            self.data = {
                key: {"rx": 0, "tx": 0, "online": value["online"]}
                for key, value in snapshot.items()
            }

        now = int(time.time())
        with connect() as c:
            for (uid, transport), value in snapshot.items():
                c.execute("""
                INSERT INTO proxy_counters(user_id,transport,rx_bytes,tx_bytes,online,last_seen)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(user_id,transport) DO UPDATE SET
                  rx_bytes=proxy_counters.rx_bytes+excluded.rx_bytes,
                  tx_bytes=proxy_counters.tx_bytes+excluded.tx_bytes,
                  online=excluded.online,
                  last_seen=CASE WHEN excluded.online>0 THEN excluded.last_seen ELSE proxy_counters.last_seen END
                """, (
                    uid, transport, value["rx"], value["tx"],
                    value["online"], now,
                ))

            c.execute("""
            UPDATE users
            SET rx_bytes=COALESCE((
                  SELECT SUM(rx_bytes) FROM proxy_counters pc WHERE pc.user_id=users.id
                ),0),
                tx_bytes=COALESCE((
                  SELECT SUM(tx_bytes) FROM proxy_counters pc WHERE pc.user_id=users.id
                ),0),
                online_count=COALESCE((
                  SELECT SUM(online) FROM proxy_counters pc WHERE pc.user_id=users.id
                ),0),
                last_seen=COALESCE((
                  SELECT MAX(last_seen) FROM proxy_counters pc WHERE pc.user_id=users.id
                ),0),
                updated_at=CURRENT_TIMESTAMP
            """)
            c.commit()

COUNTERS = CounterBuffer()
SERVERS = []

def load_endpoints():
    with connect() as c:
        rows = [dict(r) for r in c.execute("""
        SELECT * FROM users WHERE paused=0 AND status='Active'
        """)]

    result = []
    for u in rows:
        if u["openssh_enabled"] and u["openssh_port"]:
            result.append(Endpoint(u["id"], u["username"], "openssh", u["openssh_port"], None, 2222))
        if u["dropbear_enabled"] and u["dropbear_port"]:
            result.append(Endpoint(u["id"], u["username"], "dropbear", u["dropbear_port"], None, 2223))
        if u["ws_enabled"] and u["ws_port"]:
            result.append(Endpoint(u["id"], u["username"], "ws", u["ws_port"], u["ws_token"], 2222))
        if u["tls_enabled"] and u["tls_port"]:
            result.append(Endpoint(u["id"], u["username"], "tls", u["tls_port"], None, 2222))
    return result

async def pipe(reader, writer, uid, transport, direction):
    try:
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
            if direction == "rx":
                await COUNTERS.add(uid, transport, rx=len(chunk))
            else:
                await COUNTERS.add(uid, transport, tx=len(chunk))
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

async def tcp_handler(client_r, client_w, ep):
    await COUNTERS.add(ep.user_id, ep.transport, online_delta=1)
    try:
        backend_r, backend_w = await asyncio.open_connection("127.0.0.1", ep.backend_port)
        await asyncio.gather(
            pipe(client_r, backend_w, ep.user_id, ep.transport, "rx"),
            pipe(backend_r, client_w, ep.user_id, ep.transport, "tx"),
        )
    finally:
        await COUNTERS.add(ep.user_id, ep.transport, online_delta=-1)

async def ws_handler(websocket, ep):
    path = websocket.request.path
    if path != f"/ws/{ep.token}":
        await websocket.close(code=1008, reason="invalid path")
        return

    await COUNTERS.add(ep.user_id, ep.transport, online_delta=1)
    try:
        backend_r, backend_w = await asyncio.open_connection("127.0.0.1", ep.backend_port)

        async def ws_to_tcp():
            async for message in websocket:
                if isinstance(message, str):
                    message = message.encode()
                backend_w.write(message)
                await backend_w.drain()
                await COUNTERS.add(ep.user_id, ep.transport, rx=len(message))

        async def tcp_to_ws():
            while True:
                chunk = await backend_r.read(65536)
                if not chunk:
                    break
                await websocket.send(chunk)
                await COUNTERS.add(ep.user_id, ep.transport, tx=len(chunk))

        await asyncio.gather(ws_to_tcp(), tcp_to_ws())
    finally:
        await COUNTERS.add(ep.user_id, ep.transport, online_delta=-1)
        try:
            backend_w.close()
            await backend_w.wait_closed()
        except Exception:
            pass

async def start_servers():
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(Config.TLS_CERT, Config.TLS_KEY)

    for ep in load_endpoints():
        if ep.transport == "ws":
            server = await websockets.serve(
                lambda ws, endpoint=ep: ws_handler(ws, endpoint),
                "0.0.0.0", ep.port,
                max_size=None,
                ping_interval=25,
                ping_timeout=20,
            )
        else:
            context = ssl_context if ep.transport == "tls" else None
            server = await asyncio.start_server(
                lambda r, w, endpoint=ep: tcp_handler(r, w, endpoint),
                "0.0.0.0", ep.port,
                ssl=context,
            )
        SERVERS.append(server)

async def flush_loop():
    while True:
        await asyncio.sleep(5)
        await COUNTERS.flush()

async def main():
    init_db(Config.DB_PATH)
    await start_servers()
    await flush_loop()

if __name__ == "__main__":
    asyncio.run(main())
