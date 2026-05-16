"""``live_bus`` üzenet + publish viselkedés."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.services.live_bus import (
    DEFAULT_INVALIDATION_TOPICS,
    LIVE_UI_TICK_TOPICS,
    build_invalidate_message,
    clear_subscribers_for_tests,
    publish_invalidate,
    register_client,
    subscriber_count,
    unregister_client,
)


@pytest.fixture(autouse=True)
def _clean_live_bus() -> None:
    clear_subscribers_for_tests()
    yield
    clear_subscribers_for_tests()


def test_live_ui_tick_includes_orders_topics() -> None:
    assert "orders" in LIVE_UI_TICK_TOPICS
    assert LIVE_UI_TICK_TOPICS == DEFAULT_INVALIDATION_TOPICS


def test_build_invalidate_message_json() -> None:
    raw = build_invalidate_message(["dashboard", "orders"])
    data = json.loads(raw)
    assert data["type"] == "invalidate"
    assert data["topics"] == ["dashboard", "orders"]
    assert "t" in data


@pytest.mark.asyncio
async def test_publish_invalidate_calls_send_text() -> None:
    ws = AsyncMock()
    ws.send_text = AsyncMock()
    register_client(ws)
    await publish_invalidate(["positions"])
    ws.send_text.assert_awaited_once()
    unregister_client(ws)


@pytest.mark.asyncio
async def test_publish_drops_dead_clients() -> None:
    ws = AsyncMock()
    ws.send_text = AsyncMock(side_effect=OSError("boom"))
    register_client(ws)
    assert subscriber_count() == 1
    await publish_invalidate(["events"])
    assert subscriber_count() == 0
