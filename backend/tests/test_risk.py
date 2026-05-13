"""Risk / kockázat számítás tesztek."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.risk import compute_margin, compute_quantity


def test_compute_margin_uses_1_percent_of_balance() -> None:
    """100 USDT egyenleg → 1 USDT margin (1%)."""
    margin = compute_margin(Decimal("100"))
    assert margin == Decimal("1.00")


def test_compute_margin_respects_minimum_of_0_25_usdt() -> None:
    """10 USDT egyenleg → 0.10 USDT lenne 1%, de min 0.25 lép életbe."""
    margin = compute_margin(Decimal("10"))
    assert margin == Decimal("0.25")


def test_compute_margin_zero_balance_uses_minimum() -> None:
    margin = compute_margin(Decimal("0"))
    assert margin == Decimal("0.25")


def test_compute_margin_negative_balance_uses_minimum() -> None:
    margin = compute_margin(Decimal("-5"))
    assert margin == Decimal("0.25")


def test_compute_margin_custom_settings() -> None:
    """Az aránypont és a minimum mind override-olható."""
    margin = compute_margin(
        Decimal("1000"),
        pct_of_balance=Decimal("0.02"),
        minimum_usdt=Decimal("5"),
    )
    assert margin == Decimal("20.00")


def test_compute_quantity_simple() -> None:
    """margin=1 USDT × leverage=100 / price=50_000 = 0.002 BTC, kerekítve 4 tizedesre."""
    qty = compute_quantity(
        margin_usdt=Decimal("1"),
        leverage=100,
        price=Decimal("50000"),
        base_precision=4,
    )
    assert qty == Decimal("0.0020")


def test_compute_quantity_rounds_down_to_precision() -> None:
    """0.00123456 → precízió 3 → 0.001 (lefelé)."""
    qty = compute_quantity(
        margin_usdt=Decimal("0.123456"),
        leverage=1,
        price=Decimal("100"),
        base_precision=3,
    )
    assert qty == Decimal("0.001")


def test_compute_quantity_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        compute_quantity(margin_usdt=Decimal("1"), leverage=0, price=Decimal("1"))
    with pytest.raises(ValueError):
        compute_quantity(margin_usdt=Decimal("1"), leverage=1, price=Decimal("0"))
