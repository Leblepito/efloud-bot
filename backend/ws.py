"""WebSocket gateway — bot events → connected browser clients.

Single endpoint /ws. Auth via session cookie (browser sends automatically).
Each client subscribes to events.bus and forwards events as JSON over the socket.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import websockets
from fastapi import WebSocket, WebSocketDisconnect

from backend.auth import is_authenticated, COOKIE_NAME
from backend.events import bus

log = logging.getLogger("efloud.ws")


def _session_token_from_cookie(websocket: WebSocket) -> Optional[str]:
    cookie_header = websocket.headers.get("cookie", "")
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith(f"{COOKIE_NAME}="):
            return part.split("=", 1)[1]
    return None


async def websocket_handler(websocket: WebSocket) -> None:
    if not is_authenticated(_session_token_from_cookie(websocket)):
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


async def chart_ws_handler(websocket: WebSocket, symbol: str, interval: str) -> None:
    """Binance Futures kline websocket akışını sunucu üzerinden tarayıcıya relay eder.

    Tarayıcının wss://fstream.binance.com'a doğrudan bağlanması ağ/ISP
    gecikmesine takılabiliyordu (bkz. /api/chart/klines REST proxy'si ile
    aynı kök neden). Sunucu Binance'a zaten hızlı bağlandığı için akışı
    burada açıp ham mesajları olduğu gibi istemciye iletiyoruz.
    """
    from backend.api import _clean_chart_symbol, _CHART_ALLOWED_INTERVALS

    if not is_authenticated(_session_token_from_cookie(websocket)):
        await websocket.close(code=1008, reason="Not authenticated")
        return

    if interval not in _CHART_ALLOWED_INTERVALS:
        await websocket.close(code=1003, reason="Invalid interval")
        return

    clean_symbol = _clean_chart_symbol(symbol)
    # fstream.binance.com bu sunucunun IP'sinden handshake'i kabul edip veri
    # akıtmıyor (sessiz blok); resmi alternatif domain binancefuture.com
    # ayni mainnet futures verisini sorunsuz iletiyor.
    upstream_url = f"wss://fstream.binancefuture.com/ws/{clean_symbol.lower()}@kline_{interval}"

    await websocket.accept()

    client_recv_task: Optional[asyncio.Task] = None
    try:
        while True:
            try:
                async with websockets.connect(upstream_url, ping_interval=20, ping_timeout=20) as upstream:
                    if client_recv_task is None:
                        client_recv_task = asyncio.create_task(websocket.receive_text())
                    while True:
                        upstream_task = asyncio.create_task(upstream.recv())
                        done, pending = await asyncio.wait(
                            {client_recv_task, upstream_task},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if upstream_task in pending:
                            upstream_task.cancel()
                        elif upstream_task in done:
                            await websocket.send_text(upstream_task.result())

                        if client_recv_task in done:
                            # Client disconnected (raises) or sent something we ignore
                            client_recv_task.result()
                            client_recv_task = asyncio.create_task(websocket.receive_text())
            except (WebSocketDisconnect, RuntimeError):
                break
            except websockets.exceptions.ConnectionClosed:
                await asyncio.sleep(1)
                continue
            except Exception as e:
                log.warning(f"Chart WS relay error for {clean_symbol}@{interval}: {e!r}")
                await asyncio.sleep(2)
                continue
    finally:
        if client_recv_task is not None:
            client_recv_task.cancel()
        log.info(f"Chart WS relay closed for {clean_symbol}@{interval}")
