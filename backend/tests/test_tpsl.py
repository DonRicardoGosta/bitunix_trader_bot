"""Take-profit / stop-loss árszámítás tesztek."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.tpsl import (
    compute_tp_sl_prices,
    implied_price_move_pct_from_roi,
    implied_tp_roi_pct_from_price_move_pct,
    is_risky_sl_roi,
)


def test_compute_tp_sl_long_simple_round_numbers() -> None:
    """BTC 100$, lev=10, TP+100% / SL-50% → TP=110, SL=95.

    Levezetés:
      tp_move = 100% / 10 = 10% → 100 × 1.10 = 110
      sl_move =  50% / 10 =  5% → 100 × 0.95 = 95
    """
    tp, sl = compute_tp_sl_prices(
        entry_price=Decimal("100"),
        side="BUY",
        leverage=10,
        tp_roi_pct=Decimal("100"),
        sl_roi_pct=Decimal("50"),
        price_precision=2,
    )
    assert tp == Decimal("110.00")
    assert sl == Decimal("95.00")


def test_compute_tp_sl_short_inverted() -> None:
    """SHORT esetben TP lefelé, SL felfelé."""
    tp, sl = compute_tp_sl_prices(
        entry_price=Decimal("100"),
        side="SELL",
        leverage=10,
        tp_roi_pct=Decimal("100"),
        sl_roi_pct=Decimal("50"),
        price_precision=2,
    )
    assert tp == Decimal("90.00")
    assert sl == Decimal("105.00")


def test_compute_tp_sl_userspec_200_and_100_percent() -> None:
    """A user specifikációja: lev=20, TP+200%, SL-100% → mozgás 10% / 5%."""
    tp, sl = compute_tp_sl_prices(
        entry_price=Decimal("1000"),
        side="BUY",
        leverage=20,
        tp_roi_pct=Decimal("200"),
        sl_roi_pct=Decimal("100"),
        price_precision=2,
    )
    assert tp == Decimal("1100.00")
    assert sl == Decimal("950.00")


def test_compute_tp_sl_high_leverage_tightens_prices() -> None:
    """lev=100, TP+200% → +2% mozgás. SL-100% → -1% mozgás."""
    tp, sl = compute_tp_sl_prices(
        entry_price=Decimal("50000"),
        side="BUY",
        leverage=100,
        tp_roi_pct=Decimal("200"),
        sl_roi_pct=Decimal("100"),
        price_precision=2,
    )
    assert tp == Decimal("51000.00")
    assert sl == Decimal("49500.00")


def test_compute_tp_sl_rounding_directions() -> None:
    """TP nyereség-felé kerekítés, SL veszteség-felé (későbbi kilépés)."""
    # LONG: tp ROUND_DOWN (alacsonyabb TP = előbb teljesül),
    #       sl ROUND_DOWN (alacsonyabb SL = később vált ki)
    tp_long, sl_long = compute_tp_sl_prices(
        entry_price=Decimal("1.23456"),
        side="BUY",
        leverage=10,
        tp_roi_pct=Decimal("100"),
        sl_roi_pct=Decimal("50"),
        price_precision=3,
    )
    # 1.23456 * 1.10 = 1.358016 -> round_down 3 dec = 1.358
    # 1.23456 * 0.95 = 1.172832 -> round_down 3 dec = 1.172
    assert tp_long == Decimal("1.358")
    assert sl_long == Decimal("1.172")


def test_compute_tp_sl_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        compute_tp_sl_prices(
            entry_price=Decimal("0"),
            side="BUY",
            leverage=10,
            tp_roi_pct=Decimal("100"),
            sl_roi_pct=Decimal("50"),
        )
    with pytest.raises(ValueError):
        compute_tp_sl_prices(
            entry_price=Decimal("100"),
            side="BUY",
            leverage=0,
            tp_roi_pct=Decimal("100"),
            sl_roi_pct=Decimal("50"),
        )
    with pytest.raises(ValueError):
        compute_tp_sl_prices(
            entry_price=Decimal("100"),
            side="HOLD",
            leverage=10,
            tp_roi_pct=Decimal("100"),
            sl_roi_pct=Decimal("50"),
        )
    with pytest.raises(ValueError):
        compute_tp_sl_prices(
            entry_price=Decimal("100"),
            side="BUY",
            leverage=10,
            tp_roi_pct=Decimal("0"),
            sl_roi_pct=Decimal("50"),
        )


def test_implied_price_move_pct_from_roi_matches_direct_formula() -> None:
    """ROI / leverage → ugyanaz a %% mint a ``compute_tp_sl_prices`` belső aránya."""
    tp_m, sl_m = implied_price_move_pct_from_roi(
        leverage=20,
        tp_roi_pct=Decimal("200"),
        sl_roi_pct=Decimal("100"),
    )
    assert tp_m == Decimal("10")
    assert sl_m == Decimal("5")
    tp, sl = compute_tp_sl_prices(
        entry_price=Decimal("100"),
        side="BUY",
        leverage=20,
        tp_roi_pct=Decimal("200"),
        sl_roi_pct=Decimal("100"),
        price_precision=4,
    )
    assert tp == Decimal("110.0000")
    assert sl == Decimal("95.0000")


def test_implied_tp_roi_pct_inverse_of_move_from_roi() -> None:
    """tp_move × leverage ≈ eredeti TP ROI (margin %%)."""
    tp_m, _sl_m = implied_price_move_pct_from_roi(
        leverage=20,
        tp_roi_pct=Decimal("200"),
        sl_roi_pct=Decimal("100"),
    )
    assert implied_tp_roi_pct_from_price_move_pct(tp_move_pct=tp_m, leverage=20) == Decimal(
        "200"
    )


def test_implied_tp_roi_pct_from_price_move_pct_invalid() -> None:
    with pytest.raises(ValueError):
        implied_tp_roi_pct_from_price_move_pct(tp_move_pct=Decimal("1"), leverage=0)
    with pytest.raises(ValueError):
        implied_tp_roi_pct_from_price_move_pct(tp_move_pct=Decimal("0"), leverage=10)


def test_implied_price_move_pct_from_roi_invalid() -> None:
    with pytest.raises(ValueError):
        implied_price_move_pct_from_roi(
            leverage=0,
            tp_roi_pct=Decimal("100"),
            sl_roi_pct=Decimal("50"),
        )


def test_is_risky_sl_roi() -> None:
    assert is_risky_sl_roi(Decimal("100")) is True
    assert is_risky_sl_roi(Decimal("90")) is True
    assert is_risky_sl_roi(Decimal("50")) is False
