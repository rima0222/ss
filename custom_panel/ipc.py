import asyncio
import json
import socket
from typing import Any

def request(socket_path: str, payload: dict, timeout: float = 20.0) -> Any:
    raw = (json.dumps(payload, separators=(",", ":")) + "\n").encode()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(socket_path)
        sock.sendall(raw)
        response = b""
        while not response.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                break
            response += chunk
    result = json.loads(response.decode() or "{}")
    if not result.get("ok"):
        raise RuntimeError(result.get("error", "IPC request failed"))
    return result.get("result")

async def async_request(socket_path: str, payload: dict, timeout: float = 10.0) -> Any:
    reader, writer = await asyncio.wait_for(
        asyncio.open_unix_connection(socket_path),
        timeout=timeout,
    )
    try:
        writer.write((json.dumps(payload, separators=(",", ":")) + "\n").encode())
        await writer.drain()
        raw = await asyncio.wait_for(reader.readline(), timeout=timeout)
        result = json.loads(raw.decode() or "{}")
        if not result.get("ok"):
            raise RuntimeError(result.get("error", "IPC request failed"))
        return result.get("result")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
