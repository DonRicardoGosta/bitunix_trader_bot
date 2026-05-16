"""Websocketen keresztüli UI invalidáció: a kliens REST-tel frissít, a push csak jelzés.

A kapcsolatok listája thread-safe; a ``send_text`` hívások az async route /
task kontextusában futnak (ugyanazon event loop, mint a Starlette WebSocket).
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

DEFAULT_INVALIDATION_TOPICS: tuple[str, ...] = (
    "dashboard",
    "orders",
    "orders_pnl",
    "positions",
    "calibration",
    "strategies",
    "events",
    "market",
    "settings",
    "analytics",
)

_th_lock = threading.Lock()
_clients: set[Any] = set()


def register_client(websocket: Any) -> None:
    """Új websocket felvétele (elfogadás után hívd)."""
    with _th_lock:
        _clients.add(websocket)


def unregister_client(websocket: Any) -> None:
    """Lezárt vagy hibás kapcsolat eltávolítása."""
    with _th_lock:
        _clients.discard(websocket)


def subscriber_count() -> int:
    """Hány aktív websocket van (tick / terhelés döntéshez)."""
    with _th_lock:
        return len(_clients)


def clear_subscribers_for_tests() -> None:
    """Csak tesztekhez: üríti a regisztrált klienseket."""
    with _th_lock:
        _clients.clear()


def build_invalidate_message(topics: Sequence[str]) -> str:
    """JSON üzenet az invalidációs pushhoz (unit tesztekhez is)."""
    payload = {
        "type": "invalidate",
        "topics": list(topics),
        "t": datetime.now(UTC).isoformat(),
    }
    return json.dumps(payload, separators=(",", ":"))


async def publish_invalidate(topics: Iterable[str]) -> None:
    """Összes feliratkozónak elküldi az invalidációs üzenetet.

    Args:
        topics: Melyik UI-szekciók frissüljenek (a frontend ezekhez köt useEffect-et).
    """
    topic_list = list(topics)
    if not topic_list:
        return
    text = build_invalidate_message(topic_list)
    with _th_lock:
        snapshot = list(_clients)
    dead: list[Any] = []
    for ws in snapshot:
        try:
            await ws.send_text(text)
        except Exception:
            dead.append(ws)
    if dead:
        with _th_lock:
            for ws in dead:
                _clients.discard(ws)
