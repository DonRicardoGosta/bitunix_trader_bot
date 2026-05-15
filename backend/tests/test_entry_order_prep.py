"""OPEN belépés előkészítés: leverage + TP/SL egy place_order híváshoz."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.trading import OrderRequest
from app.services.entry_order_prep import prepare_open_entry_order


@pytest.mark.asyncio
async def test_prepare_open_skips_when_tp_sl_present() -> None:
    client = AsyncMock()
    session = AsyncMock()
    payload = OrderRequest.model_validate(
        {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "orderType": "MARKET",
            "quantity": "0.01",
            "leverage": 10,
            "tpPrice": "110",
            "slPrice": "90",
        }
    )
    out = await prepare_open_entry_order(client=client, session=session, payload=payload)
    client.change_leverage.assert_awaited_once()
    client.get_ticker.assert_not_awaited()
    assert out.tp_price == Decimal("110")
    assert out.sl_price == Decimal("90")


@pytest.mark.asyncio
async def test_prepare_open_fills_missing_tp_sl_from_calibration() -> None:
    client = AsyncMock()
    client.get_ticker.return_value = {
        "data": [{"symbol": "BTCUSDT", "lastPrice": "100"}],
    }
    client.get_trading_pairs.return_value = {
        "data": [
            {
                "symbol": "BTCUSDT",
                "maxLeverage": 20,
                "pricePrecision": 2,
                "basePrecision": 4,
            }
        ]
    }
    session = AsyncMock()

    calibration = MagicMock()
    calibration.lookup.return_value = (Decimal("1.5"), Decimal("0.75"))

    payload = OrderRequest.model_validate(
        {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "orderType": "MARKET",
            "quantity": "0.01",
            "leverage": 10,
        }
    )

    import app.services.entry_order_prep as mod

    original = mod.get_active_calibration_result
    mod.get_active_calibration_result = AsyncMock(return_value=calibration)  # type: ignore[method-assign]
    try:
        out = await prepare_open_entry_order(client=client, session=session, payload=payload)
    finally:
        mod.get_active_calibration_result = original
    assert out.tp_price is not None
    assert out.sl_price is not None
    assert out.tp_price > Decimal("100")
    assert out.sl_price < Decimal("100")
