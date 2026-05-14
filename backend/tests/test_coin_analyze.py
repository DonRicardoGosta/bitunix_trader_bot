"""``coin_analyze`` service: kline terv + swing elemzés."""

from __future__ import annotations

from decimal import Decimal

from app.services import coin_analyze as coin_analyze_mod
from app.services.coin_analyze import (
    analyze_clean_legs,
    build_walk_forward_payload,
    build_walk_forward_sequence,
    build_walk_forward_tpsl_variations_payload,
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
    touch, off, amb = coin_analyze_mod._simulate_tp_sl(
        bars, entry=entry, tp_move_pct=move, sl_move_pct=move, side="long"
    )
    assert touch == "tp" and off == 0 and amb is False


def test_simulate_long_asymmetric_tp_tighter_than_sl() -> None:
    """Kisebb TP, nagyobb SL: előbb TP érinthető."""
    entry = Decimal("100")
    bars = [
        {
            "time": Decimal(1),
            "open": Decimal("100"),
            "high": Decimal("100.4"),
            "low": Decimal("99"),
            "close": Decimal("100.1"),
        }
    ]
    touch, off, amb = coin_analyze_mod._simulate_tp_sl(
        bars,
        entry=entry,
        tp_move_pct=Decimal("0.3"),
        sl_move_pct=Decimal("2"),
        side="long",
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


def test_clip_variation_tpsl_move_pct() -> None:
    """Csak felső korlát: kicsi érték változatlan; nagy levágódik."""
    lo = coin_analyze_mod._clip_variation_tpsl_move_pct(Decimal("1"), Decimal("5"))
    assert lo == (Decimal("1"), Decimal("5"))
    hi = coin_analyze_mod._clip_variation_tpsl_move_pct(Decimal("500"), Decimal("200"))
    assert hi == (Decimal("300"), Decimal("150"))


def test_variation_meets_min_tpsl_pct_profile() -> None:
    assert (
        coin_analyze_mod._variation_meets_min_tpsl_pct_profile(
            Decimal("30"), Decimal("10")
        )
        is True
    )
    assert (
        coin_analyze_mod._variation_meets_min_tpsl_pct_profile(
            Decimal("29.9"), Decimal("10")
        )
        is False
    )
    assert (
        coin_analyze_mod._variation_meets_min_tpsl_pct_profile(
            Decimal("30"), Decimal("9")
        )
        is False
    )


def test_count_trades_entry_in_last_24h() -> None:
    # idő mp-ben (<1e11) → _to_int_ms szoroz 1000-zel
    klines = [
        {
            "time": Decimal(100_000_000),
            "open": Decimal(1),
            "high": Decimal(2),
            "low": Decimal(1),
            "close": Decimal(1),
        }
    ]
    end_ms = 100_000_000 * 1000
    start_ms = end_ms - 24 * 60 * 60 * 1000
    trades = [
        {"entry_time_ms": start_ms - 1},
        {"entry_time_ms": start_ms},
        {"entry_time_ms": start_ms + 1_000_000},
        {"entry_time_ms": end_ms},
    ]
    n = coin_analyze_mod._count_trades_with_entry_in_last_hours(
        klines, trades, hours=24
    )
    assert n == 3


def test_split_half_matches_time_midpoint() -> None:
    klines = [_synth_bar(i * 60_000, "100") for i in range(40)]
    a = split_klines_at_time_fraction(klines, Decimal("0.5"))
    b = split_klines_time_midpoint(klines)
    assert a is not None and b is not None
    assert len(a[0]) == len(b[0]) and len(a[1]) == len(b[1])


def test_build_tpsl_variations_payload_grid() -> None:
    klines = [_synth_bar(i * 60_000, str(100 + (i % 5))) for i in range(50)]
    v = build_walk_forward_tpsl_variations_payload(
        klines, choppiness_max=Decimal("1.72"), cooldown_minutes=0
    )
    assert 1 <= len(v["variations"]) <= 36
    assert v["variations"][0]["rank"] == 0
    assert "has_recommended_variation" in v
    assert "is_recommended" in v["variations"][0]
    assert sum(1 for row in v["variations"] if row["is_recommended"]) <= 1


def test_exclude_variation_last_window_single_unresolved() -> None:
    t_end = 200_000_000_000  # ms — _to_int_ms ne szorozzon
    klines = [_synth_bar(t_end, "100")]
    two = [
        {"entry_time_ms": t_end - 1, "first_touch": "none"},
        {"entry_time_ms": t_end, "first_touch": "none"},
    ]
    assert (
        coin_analyze_mod._exclude_variation_last_window_single_unresolved(klines, two)
        is False
    )
    one_none = [{"entry_time_ms": t_end, "first_touch": "none"}]
    assert (
        coin_analyze_mod._exclude_variation_last_window_single_unresolved(
            klines, one_none
        )
        is True
    )
    one_tp = [{"entry_time_ms": t_end, "first_touch": "tp"}]
    assert (
        coin_analyze_mod._exclude_variation_last_window_single_unresolved(
            klines, one_tp
        )
        is False
    )


def test_trade_forward_window_bars_chunk() -> None:
    assert coin_analyze_mod._trade_forward_window_bars(100) == 33
    assert coin_analyze_mod._trade_forward_window_bars(10) == 10
    assert (
        coin_analyze_mod._trade_forward_window_bars(30, max_trade_forward_bars=5) == 5
    )


def test_walk_forward_sequence_horizon_allows_multiple_trades() -> None:
    klines = [
        _synth_bar(1_500_000_000_000 + i * 60_000, str(100 + (i % 3)))
        for i in range(120)
    ]
    seq = coin_analyze_mod._build_walk_forward_sequence_core(
        klines,
        choppiness_max=Decimal("5"),
        tp_median_multiplier=Decimal("2"),
        sl_median_multiplier=Decimal("2"),
        cooldown_minutes=0,
        clip_variation_tpsl_bounds=True,
    )
    assert len(seq["trades"]) >= 2


def test_build_walk_forward_sequence_returns_current_signal() -> None:
    klines = [_synth_bar(i * 60_000, str(100 + (i % 5))) for i in range(50)]
    seq = build_walk_forward_sequence(
        klines, choppiness_max=Decimal("1.72"), cooldown_minutes=0
    )
    assert "current_signal" in seq
    assert isinstance(seq["trades"], list)
    assert seq.get("tp_median_multiplier") == "0.5"


def test_run_walk_forward_includes_tp_sl_prices() -> None:
    klines = [_synth_bar(i * 60_000, str(100 + (i % 5))) for i in range(50)]
    wf = build_walk_forward_payload(klines)
    assert wf.get("aggregate") is not None or wf["enabled"] is False
    if wf["enabled"]:
        assert wf.get("tp_price") is not None
        assert wf.get("sl_price") is not None
        assert wf.get("train_start_time_ms") is not None


def test_build_walk_forward_payload_has_shape() -> None:
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
