"""resolve_open_position_id + attach_full_position_tp_sl tesztek."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.services.entry_order_prep import (
    attach_full_position_tp_sl,
    resolve_open_position_id,
)


@pytest.mark.asyncio
async def test_resolve_open_position_id_finds_matching_side() -> None:
    client = AsyncMock()
    client.get_positions.return_value = {
        "data": [
            {
                "symbol": "ETHUSDT",
                "side": "BUY",
                "positionId": "p-eth",
                "qty": "0.5",
            }
        ]
    }
    pid = await resolve_open_position_id(client, symbol="ETHUSDT", side="BUY")
    assert pid == "p-eth"


@pytest.mark.asyncio
async def test_attach_full_position_tp_sl_dry_run() -> None:
    client = AsyncMock()
    client.place_position_tp_sl_order.return_value = {"dryRun": True, "data": {}}
    await attach_full_position_tp_sl(
        client,
        symbol="BTCUSDT",
        side="BUY",
        tp_price=Decimal("110"),
        sl_price=Decimal("90"),
        tp_stop_type="MARK_PRICE",
        sl_stop_type="MARK_PRICE",
        dry_run_entry=True,
    )
    client.place_position_tp_sl_order.assert_awaited_once()
    call = client.place_position_tp_sl_order.await_args.kwargs
    assert call["position_id"] == "dry-run-position"
    assert call["tp_price"] == Decimal("110")
