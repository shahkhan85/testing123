#!/usr/bin/env python3
"""Simple WebSocket echo server for testing the decoder."""

import asyncio
try:
    import websockets
except ImportError:
    print("websockets not installed. Run: pip3 install websockets")
    raise SystemExit(1)

PORT = 8765


async def handler(ws):
    addr = ws.remote_address
    print(f"[server] client connected: {addr}")
    try:
        async for message in ws:
            if isinstance(message, bytes):
                print(f"[server] binary ({len(message)} bytes) — echoing")
            else:
                print(f"[server] text: {message!r} — echoing")
            await ws.send(message)
    except websockets.ConnectionClosed:
        print(f"[server] client disconnected: {addr}")


async def main():
    print(f"[server] listening on ws://127.0.0.1:{PORT}")
    async with websockets.serve(handler, "127.0.0.1", PORT):
        await asyncio.Future()   # run forever


if __name__ == "__main__":
    asyncio.run(main())
