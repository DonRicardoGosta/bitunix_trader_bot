"""Hold-window pozíció monitor tesztek."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bitunix.exceptions import BitunixAPIError
from app.db.models import Order, OrderSide, OrderStatus, OrderType
from app.services.entry_order_prep import OpenEntryPreparationError
from app.services.position_hold_monitor import (
    _handle_hold_exit_place_failed,
    _mark_hold_exit_done,
    _try_hold_window_exit,
)


def _sample_open_order(*, ctx: dict | None = None) -> Order:
    return Order(
        id=1,
        client_order_id="bt-test-open",
        symbol="ZORAUSDT",
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        quantity=Decimal("1000"),
        leverage=20,
        status=OrderStatus.FILLED,
        reduce_only=False,
        strategy_name="top_signal_entries",
        entry_context=ctx
        or {
            "hold_window_optimization_enabled": True,
            "hold_window_minutes": 30,
        },
        created_at=datetime.now(UTC) - timedelta(minutes=45),
    )


@pytest.mark.asyncio
async def test_try_hold_window_exit_marks_done_when_no_position() -> None:
    session = AsyncMock()
    trading = AsyncMock()
    client = AsyncMock()
    order = _sample_open_order()

    with patch(
        "app.services.position_hold_monitor.resolve_open_position_for_exit",
        new_callable=AsyncMock,
        side_effect=OpenEntryPreparationError("nincs pozíció"),
    ):
        result = await _try_hold_window_exit(session, trading, client, order)

    assert result == 0
    assert order.entry_context["hold_time_exit_done"] is True
    assert order.entry_context["hold_time_exit_reason"] == "position_not_on_exchange"
    trading.place_order.assert_not_awaited()
    session.add.assert_called()


@pytest.mark.asyncio
async def test_try_hold_window_exit_uses_exchange_qty() -> None:
    session = AsyncMock()
    trading = AsyncMock()
    client = AsyncMock()
    order = _sample_open_order()

    with patch(
        "app.services.position_hold_monitor.resolve_open_position_for_exit",
        new_callable=AsyncMock,
        return_value=("pos-1", Decimal("42.5")),
    ):
        result = await _try_hold_window_exit(session, trading, client, order)

    assert result == 1
    trading.place_order.assert_awaited_once()
    close_req = trading.place_order.await_args.args[0]
    assert close_req.quantity == Decimal("42.5")
    assert close_req.position_id == "pos-1"
    assert order.entry_context["hold_time_exit_done"] is True


@pytest.mark.asyncio
async def test_handle_insufficient_amount_marks_done_after_max_failures() -> None:
    session = AsyncMock()
    order = _sample_open_order(ctx={"hold_time_exit_fail_count": 2})
    exc = BitunixAPIError("Insufficient amount", code="20008")

    result = await _handle_hold_exit_place_failed(
        session, order, sym="ZORAUSDT", exc=exc
    )

    assert result == 0
    assert order.entry_context["hold_time_exit_done"] is True
    assert order.entry_context["hold_time_exit_reason"] == "exit_failed_insufficient_amount"
    assert order.entry_context["hold_time_exit_fail_count"] == 3


@pytest.mark.asyncio
async def test_mark_hold_exit_done_sets_context_flags() -> None:
    session = MagicMock()
    order = _sample_open_order()
    await _mark_hold_exit_done(session, order, reason="time_exit_placed")
    assert order.entry_context["hold_time_exit_done"] is True
    assert order.entry_context["hold_time_exit_reason"] == "time_exit_placed"
