"""Trading service segédfüggvények tesztelése."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.trading import estimate_notional


@pytest.mark.asyncio
async def test_estimate_notional_simple() -> None:
    notional = await estimate_notional(
        quantity=Decimal("1"), price=Decimal("50000"), leverage=10
    )
    assert notional == Decimal("5000")


@pytest.mark.asyncio
async def test_estimate_notional_invalid_leverage() -> None:
    with pytest.raises(ValueError):
        await estimate_notional(
            quantity=Decimal("1"), price=Decimal("10"), leverage=0
        )
