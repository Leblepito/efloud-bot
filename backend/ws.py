"""WebSocket gateway — bot events → connected browser clients.

Single endpoint /ws. Auth via session cookie (browser sends automatically).
Each client subscribes to events.bus and forwards events as JSON over the socket.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

from backend.auth import is_authenticated, COOKIE_NAME
from backend.events import bus

log = logging.getLogger("efloud.ws")


async def websocket_handler(websocket: WebSocket) -> None:
    # Auth via cookie
    cookie_header = websocket.headers.get("cookie", "")
    session_token: Optional[str] = None
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith(f"{COOKIE_NAME}="):
            session_token = part.split("=", 1)[1]
            break

    if not is_authenticated(session_token):
        await websocket.close(code=1008, reason="Not authenticated")
        return

    await websocket.accept()
    queue = await bus.subscribe()

    log.info(f"WS client connected (subscribers: {bus.subscriber_count})")

    # Send a hello event so client knows connection is live
    await websocket.send_json({"type": "hello", "payload": {"subscribers": bus.subscriber_count}})

    try:
        while True:
            # Race: either receive client ping/close OR forward event
            recv_task = asyncio.create_task(websocket.receive_text())
            event_task = asyncio.create_task(queue.get())
            done, pending = await asyncio.wait(
                {recv_task, event_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()

            if recv_task in done:
                # Client sent something (heartbeat or close)
                try:
                    msg = recv_task.result()
                    # Could parse for ping/pong, but for now ignore
                    if msg == "ping":
                        await websocket.send_text("pong")
                except WebSocketDisconnect:
                    break
                except Exception:
                    break

            if event_task in done:
                evt = event_task.result()
                try:
                    await websocket.send_json(evt.to_dict())
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    finally:
        await bus.unsubscribe(queue)
        log.info(f"WS client disconnected (subscribers: {bus.subscriber_count})")
