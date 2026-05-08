#!/usr/bin/env python3
"""WebSocket test client — sends text, binary, and ping frames."""

import asyncio
import json
import os
try:
    import websockets
except ImportError:
    print("websockets not installed. Run: pip3 install websockets")
    raise SystemExit(1)

URL = "ws://127.0.0.1:8765"


async def main():
    print(f"[client] connecting to {URL}")
    async with websockets.connect(URL) as ws:

        # 1. Plain text
        await ws.send("Hello, WebSocket decoder!")
        reply = await ws.recv()
        print(f"[client] echo: {reply!r}")

        # 2. JSON payload
        payload = json.dumps({"event": "test", "value": 42, "items": [1, 2, 3]})
        await ws.send(payload)
        reply = await ws.recv()
        print(f"[client] echo: {reply!r}")

        # 3. Binary frame
        binary_data = os.urandom(16)
        await ws.send(binary_data)
        reply = await ws.recv()
        print(f"[client] echo: {len(reply)} binary bytes")

        # 4. Ping (websockets library handles pong automatically,
        #    but the decoder will still see the frames on the wire)
        await ws.ping()
        print("[client] ping sent")

        # 5. Long text (>125 bytes — exercises the 16-bit length field)
        long_msg = "A" * 300
        await ws.send(long_msg)
        reply = await ws.recv()
        print(f"[client] long echo: {len(reply)} chars")

        print("[client] all tests sent — closing")

    print("[client] connection closed")


if __name__ == "__main__":
    asyncio.run(main())
