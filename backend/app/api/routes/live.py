"""Élő UI push: WebSocket invalidáció (a tényleges adat továbbra is REST-en)."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.live_bus import register_client, unregister_client

router = APIRouter(tags=["live"])


@router.websocket("/live/stream")
async def live_stream(websocket: WebSocket) -> None:
    """Nyitott kapcsolat: a szerver JSON invalidációs üzeneteket küld.

    A kliens opcionálisan küldhet bármilyen szöveget (keepalive); üresen is
    tartható a kapcsolat, amíg a böngésző be nem zárja.
    """
    await websocket.accept()
    register_client(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        unregister_client(websocket)
