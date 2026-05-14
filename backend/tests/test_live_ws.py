"""WebSocket ``/api/live/stream`` smoke: kapcsolódás."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_live_stream_websocket_accepts(client: TestClient) -> None:
    with client.websocket_connect("/api/live/stream") as ws:
        assert ws is not None
