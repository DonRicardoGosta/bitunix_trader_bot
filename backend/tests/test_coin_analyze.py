"""``coin_analyze`` service: kline terv + swing elemzés."""

from __future__ import annotations

from decimal import Decimal

from app.services import coin_analyze as coin_analyze_mod
from app.services.coin_analyze import (
    analyze_clean_legs,
    build_walk_forward_payload,
    leg_choppiness,
    merge_same_side_swings,
    plan_kline_interval,
    split_klines_at_time_fraction,
    split_klines_time_midpoint,
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


def _synth_bar(t_ms: int, close: str, spread: str = "0.5") -> dict[str, Decimal]:
    c = Decimal(close)
    s = Decimal(spread)
    t = Decimal(t_ms)
    return {"time": t, "open": c, "high": c + s, "low": c - s, "close": c}


def test_split_klines_time_midpoint_splits() -> None:
    klines = [_synth_bar(i * 60_000, "100") for i in range(40)]
    out = split_klines_time_midpoint(klines)
    assert out is not None
    train, test, _ = out
    assert len(train) >= 15 and len(test) >= 5
    assert len(train) + len(test) == 40


def test_simulate_long_tp_before_sl() -> None:
    entry = Decimal("100")
    move = Decimal("1")
    bars = [
        {
            "time": Decimal(1),
            "open": Decimal("100"),
            "high": Decimal("101.5"),
            "low": Decimal("99.5"),
            "close": Decimal("100.2"),
        }
    ]
    touch, off, amb = coin_analyze_mod._simulate_symmetric_tp_sl(
        bars, entry=entry, move_pct=move, side="long"
    )
    assert touch == "tp" and off == 0 and amb is False


def test_simulate_long_same_bar_both_counts_sl() -> None:
    entry = Decimal("100")
    move = Decimal("1")
    bars = [
        {
            "time": Decimal(1),
            "open": Decimal("100"),
            "high": Decimal("102"),
            "low": Decimal("98"),
            "close": Decimal("100"),
        }
    ]
    touch, off, amb = coin_analyze_mod._simulate_symmetric_tp_sl(
        bars, entry=entry, move_pct=move, side="long"
    )
    assert touch == "sl" and amb is True


def test_split_half_matches_time_midpoint() -> None:
    klines = [_synth_bar(i * 60_000, "100") for i in range(40)]
    a = split_klines_at_time_fraction(klines, Decimal("0.5"))
    b = split_klines_time_midpoint(klines)
    assert a is not None and b is not None
    assert len(a[0]) == len(b[0]) and len(a[1]) == len(b[1])


def test_run_walk_forward_includes_tp_sl_prices() -> None:
    klines = [_synth_bar(i * 60_000, str(100 + (i % 5))) for i in range(50)]
    wf = build_walk_forward_payload(klines)
    assert wf.get("aggregate") is not None or wf["enabled"] is False
    if wf["enabled"]:
        assert wf.get("tp_price") is not None
        assert wf.get("sl_price") is not None
        assert wf.get("train_start_time_ms") is not None
    klines = [_synth_bar(i * 60_000, str(100 + (i % 5))) for i in range(40)]
    wf = build_walk_forward_payload(klines)
    assert isinstance(wf["enabled"], bool)
    if wf["train_bar_count"] > 0:
        assert wf["train_bar_count"] + wf["test_bar_count"] == 40


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
