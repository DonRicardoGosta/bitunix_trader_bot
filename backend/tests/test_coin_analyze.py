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


def test_analyze_clean_legs_many_swings_no_strict_zip_error() -> None:
    """Regression: pairwise swing legs must not use strict zip (len n vs n-1)."""

    def bar(t: int, close: int, spread: int = 1) -> dict[str, Decimal]:
        c = Decimal(close)
        s = Decimal(spread)
        return {
            "time": Decimal(t),
            "open": c,
            "high": c + s,
            "low": c - s,
            "close": c,
        }

    klines = [bar(i, 100 + (i % 5) * 3 + (i // 10)) for i in range(50)]
    clean, stats = analyze_clean_legs(klines)
    assert stats["all_leg_count"] >= 1
    assert isinstance(stats.get("median_move_pct"), (Decimal, type(None)))
    assert isinstance(clean, list)
