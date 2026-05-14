"""``coin_analyze`` service: kline terv + swing elemzés."""

from __future__ import annotations

from decimal import Decimal

from app.services.coin_analyze import (
    analyze_clean_legs,
    leg_choppiness,
    merge_same_side_swings,
    plan_kline_interval,
)


def test_plan_kline_interval_one_hour_uses_1m() -> None:
    iv, lim = plan_kline_interval(60)
    assert iv == "1m"
    assert lim == 60


def test_plan_kline_interval_one_day_uses_15m_or_finer_cap() -> None:
    iv, lim = plan_kline_interval(1440)
    assert iv == "15m"
    assert lim == 96


def test_merge_same_side_keeps_higher_high() -> None:
    merged = merge_same_side_swings(
        [
            (2, "H", Decimal("100")),
            (4, "H", Decimal("102")),
            (6, "L", Decimal("98")),
        ]
    )
    assert merged == [(4, "H", Decimal("102")), (6, "L", Decimal("98"))]


def test_leg_choppiness_straight_line_equals_one() -> None:
    closes = [Decimal(i) for i in range(10)]
    assert leg_choppiness(closes, 0, 9) == Decimal(1)


def test_analyze_clean_legs_empty_when_too_few_bars() -> None:
    klines = [
        {
            "time": Decimal(i),
            "open": Decimal(1),
            "high": Decimal(1),
            "low": Decimal(1),
            "close": Decimal(1),
        }
        for i in range(4)
    ]
    clean, stats = analyze_clean_legs(klines)
    assert clean == []
    assert stats["clean_leg_count"] == 0
