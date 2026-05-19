"""symbol_leverage segéd tesztek."""

from __future__ import annotations

import pytest

from app.services.risk import effective_order_leverage
from app.services.symbol_leverage import (
    SymbolLeverageError,
    resolve_leverage_for_symbol,
)
from app.services.trading_pairs_meta import PairMeta


def test_resolve_leverage_uses_pair_max_capped() -> None:
    meta = {
        "HIGH": PairMeta(
            symbol="HIGH",
            max_leverage=200,
            base_precision=3,
            price_precision=2,
        ),
    }
    eff, pair_max = resolve_leverage_for_symbol("HIGH", meta)
    assert pair_max == 200
    assert eff == effective_order_leverage(200)
    assert eff == 125


def test_resolve_leverage_missing_symbol_raises() -> None:
    with pytest.raises(SymbolLeverageError):
        resolve_leverage_for_symbol("MISSING", {})


@pytest.mark.asyncio
async def test_ensure_symbol_max_leverage_calls_api() -> None:
    from app.services.symbol_leverage import ensure_symbol_max_leverage

    class _Client:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def change_leverage(self, **kwargs) -> dict:
            self.calls.append(kwargs)
            return {}

    meta = {
        "BTCUSDT": PairMeta(
            symbol="BTCUSDT",
            max_leverage=75,
            base_precision=3,
            price_precision=2,
        ),
    }
    client = _Client()
    eff, pair_max = await ensure_symbol_max_leverage(
        client,  # type: ignore[arg-type]
        symbol="btcusdt",
        pair_meta=meta,
        margin_coin="USDT",
    )
    assert eff == 75
    assert pair_max == 75
    assert client.calls == [
        {"symbol": "BTCUSDT", "leverage": 75, "margin_coin": "USDT"}
    ]
