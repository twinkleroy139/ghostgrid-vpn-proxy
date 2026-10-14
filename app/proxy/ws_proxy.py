import asyncio
import logging
from typing import Optional
from fastapi import WebSocket, WebSocketDisconnect
import websockets

logger = logging.getLogger("ghostgrid.ws_proxy")


async def proxy_websocket(client_ws: WebSocket, target_ws_url: str) -> None:
    """
    Establishes an async bidirectional tunnel between client browser WebSocket
    and upstream target WebSocket endpoint.
    """
    await client_ws.accept()

    try:
        async with websockets.connect(target_ws_url) as upstream_ws:

            async def client_to_upstream():
                try:
                    while True:
                        msg = await client_ws.receive()
                        if "text" in msg:
                            await upstream_ws.send(msg["text"])
                        elif "bytes" in msg:
                            await upstream_ws.send(msg["bytes"])
                except (WebSocketDisconnect, asyncio.CancelledError):
                    pass

            async def upstream_to_client():
                try:
                    async for msg in upstream_ws:
                        if isinstance(msg, str):
                            await client_ws.send_text(msg)
                        elif isinstance(msg, bytes):
                            await client_ws.send_bytes(msg)
                except (WebSocketDisconnect, asyncio.CancelledError):
                    pass

            # Run both streaming directions concurrently
            await asyncio.gather(
                client_to_upstream(),
                upstream_to_client(),
                return_exceptions=True,
            )

    except Exception as exc:
        logger.error("WebSocket proxy error for %s: %s", target_ws_url, exc)
    finally:
        try:
            await client_ws.close()
        except Exception:
            pass