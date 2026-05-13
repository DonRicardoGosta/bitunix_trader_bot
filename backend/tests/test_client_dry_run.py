"""Bitunix kliens dry-run viselkedés tesztek."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.bitunix.client import BitunixClient


@pytest.mark.asyncio
async def test_place_order_dry_run_does_not_send_http() -> None:
    """Ha live_trading=False, a klienst NEM hívja meg a hálózat."""
    client = BitunixClient(
        api_key="ak", api_secret="sk", live_trading=False
    )
    try:
        result = await client.place_order(
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity=Decimal("0.01"),
        )
    finally:
        await client.close()

    assert result["dryRun"] is True
    assert result["echo"]["symbol"] == "BTCUSDT"
    assert result["echo"]["side"] == "BUY"
    assert result["echo"]["tradeSide"] == "OPEN"
    assert "leverage" not in result["echo"]


@pytest.mark.asyncio
async def test_cancel_order_dry_run() -> None:
    client = BitunixClient(api_key="ak", api_secret="sk", live_trading=False)
    try:
        result = await client.cancel_order(symbol="BTCUSDT", order_id="12345")
    finally:
        await client.close()
    assert result["dryRun"] is True
    assert result["echo"]["orderId"] == "12345"
