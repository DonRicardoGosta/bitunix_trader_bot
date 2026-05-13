"""Bitunix WebSocket kapcsolat-kezelő (egyszerű, újrakapcsolódó).

Publikus csatornákhoz (trade/kline/depth) használható. A privát csatornához
külön login üzenet kell, ez kibővíthető a jövőben.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

import structlog
import websockets
from websockets.exceptions import ConnectionClosed

log = structlog.get_logger(__name__)


class BitunixPublicWS:
    """Publikus WS csatornák figyelése automatikus újrakapcsolódással."""

    def __init__(self, url: str = "wss://fapi.bitunix.com/public/") -> None:
        self._url = url
        self._stop = asyncio.Event()

    async def stream(
        self,
        subscriptions: list[dict[str, Any]],
        *,
        on_message: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
        ping_interval: float = 15.0,
    ) -> AsyncIterator[dict[str, Any]]:
        """Bekapcsolódik és kibocsát üzeneteket.

        Args:
            subscriptions: pl. ``[{"op": "subscribe", "args": [{"channel": "ticker", "symbol": "BTCUSDT"}]}]``
            on_message: opcionális callback; hibák naplózva.
            ping_interval: keep-alive ping másodpercben.
        """
        backoff = 1.0
        while not self._stop.is_set():
            try:
                async with websockets.connect(self._url, ping_interval=None) as ws:
                    log.info("bitunix.ws.connected", url=self._url)
                    for sub in subscriptions:
                        await ws.send(json.dumps(sub))

                    pinger = asyncio.create_task(self._ping_loop(ws, ping_interval))
                    try:
                        async for raw in ws:
                            try:
                                msg = json.loads(raw)
                            except json.JSONDecodeError:
                                continue
                            if on_message:
                                try:
                                    await on_message(msg)
                                except Exception:
                                    log.exception("bitunix.ws.callback_error")
                            yield msg
                    finally:
                        pinger.cancel()
                backoff = 1.0
            except (ConnectionClosed, OSError) as exc:
                log.warning("bitunix.ws.disconnected", error=str(exc))
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    async def stop(self) -> None:
        self._stop.set()

    @staticmethod
    async def _ping_loop(ws: Any, interval: float) -> None:
        try:
            while True:
                await asyncio.sleep(interval)
                await ws.send(json.dumps({"op": "ping"}))
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("bitunix.ws.ping_error")
