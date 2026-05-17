"""``coin_analyze`` service: kline terv + swing elemzés."""

from __future__ import annotations

from decimal import Decimal

from app.services import coin_analyze as coin_analyze_mod
from app.services.hold_window import HoldWindowParams
from app.services.coin_analyze import (
    analyze_clean_legs,
    build_coin_analysis_payload,
    build_walk_forward_payload,
    build_walk_forward_sequence,
    build_walk_forward_tpsl_variations_payload,
    leg_choppiness,
    merge_same_side_swings,
    interval_bar_minutes,
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


def test_interval_bar_minutes() -> None:
    assert interval_bar_minutes("15m") == 15
    assert interval_bar_minutes("1m") == 1


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


def test_coerce_sl_move_pct_le_tp() -> None:
    assert coin_analyze_mod._coerce_sl_move_pct_le_tp(Decimal("5"), Decimal("3")) == (
        Decimal("5"),
        Decimal("3"),
    )
    assert coin_analyze_mod._coerce_sl_move_pct_le_tp(Decimal("5"), Decimal("8")) == (
        Decimal("5"),
        Decimal("5"),
    )


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


def test_count_trades_entry_in_last_48h() -> None:
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
    start_ms = end_ms - 48 * 60 * 60 * 1000
    trades = [
        {"entry_time_ms": start_ms - 1},
        {"entry_time_ms": start_ms},
        {"entry_time_ms": start_ms + 1_000_000},
        {"entry_time_ms": end_ms},
    ]
    n = coin_analyze_mod._count_trades_with_entry_in_last_hours(
        klines, trades, hours=48
    )
    assert n == 3


def test_compute_tp_win_rate_unresolved_not_success() -> None:
    """3 TP + 2 feloldatlan → 60%%, nem 100%% (régi TP/(TP+SL) hiba)."""
    rate = coin_analyze_mod._compute_tp_win_rate_pct(3, 0, 2, min_trades=2)
    assert rate is not None
    assert rate == Decimal("60.00")
    assert coin_analyze_mod._compute_tp_win_rate_pct(
        3, 0, 2, min_trades=10
    ) is None


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


def test_walk_forward_live_gate_ok(monkeypatch) -> None:
    def fake_build(*args, **kwargs):
        return {
            "enabled": True,
            "has_recommended_variation": True,
            "target_tp_win_rate_pct": "80",
            "best_current_signal": {
                "enabled": True,
                "predicted_side": "long",
                "tp_move_pct": "3.1",
                "sl_move_pct": "2.4",
                "prediction_reason": "median_up",
            },
            "variations": [
                {
                    "is_recommended": True,
                    "rank": 0,
                    "label": "tp0.5_sl0.35",
                    "resolved_tp_win_rate_pct": "90.00",
                    "meets_target": True,
                    "meets_min_tpsl_pct_profile": True,
                    "trades_entered_last_48h_count": 6,
                    "resolved_count": 10,
                    "tp_median_multiplier": "0.5",
                    "sl_median_multiplier": "0.35",
                },
                {"is_recommended": False},
            ],
        }

    monkeypatch.setattr(
        coin_analyze_mod, "build_walk_forward_tpsl_variations_payload", fake_build
    )
    r = coin_analyze_mod.walk_forward_live_gate_from_klines(
        [], choppiness_max=Decimal("1.72")
    )
    assert r["ok"] is True
    assert r["side"] == "BUY"
    assert r["tp_move_pct"] == Decimal("3.1")
    assert r["sl_move_pct"] == Decimal("2.4")
    assert r["wf_gate_source"] == "ui_profile_recommendation"
    assert r["wf_target_tp_win_rate_pct"] == "80"
    snap = r.get("wf_variation_snapshot")
    assert isinstance(snap, dict)
    assert snap.get("tp_median_multiplier") == "0.5"
    assert snap.get("resolved_tp_win_rate_pct") == "90.00"


def test_walk_forward_live_gate_no_recommend(monkeypatch) -> None:
    def fake_build(*args, **kwargs):
        return {"enabled": True, "has_recommended_variation": False, "variations": []}

    monkeypatch.setattr(
        coin_analyze_mod, "build_walk_forward_tpsl_variations_payload", fake_build
    )
    r = coin_analyze_mod.walk_forward_live_gate_from_klines(
        [], choppiness_max=Decimal("1.72")
    )
    assert r["ok"] is False
    assert r["reason"] == "walk_forward_no_eligible_variation"


def test_walk_forward_live_gate_grid_meets_target_fallback(monkeypatch) -> None:
    def fake_build(*args, **kwargs):
        return {
            "enabled": True,
            "has_recommended_variation": False,
            "best_current_signal": None,
            "target_tp_win_rate_pct": "80",
            "variations": [
                {
                    "rank": 0,
                    "label": "tp0.65_sl0.65",
                    "resolved_tp_win_rate_pct": "100.00",
                    "tp_median_multiplier": "0.65",
                    "sl_median_multiplier": "0.65",
                    "meets_target": True,
                    "trades_entered_last_48h_count": 5,
                    "meets_min_tpsl_pct_profile": False,
                    "resolved_count": 5,
                }
            ],
        }

    def fake_compute(*args, **kwargs):
        return {
            "enabled": True,
            "predicted_side": "short",
            "tp_move_pct": "10",
            "sl_move_pct": "5",
            "prediction_reason": "clean_legs_down_majority",
        }

    monkeypatch.setattr(
        coin_analyze_mod, "build_walk_forward_tpsl_variations_payload", fake_build
    )
    monkeypatch.setattr(coin_analyze_mod, "_compute_current_signal", fake_compute)
    r = coin_analyze_mod.walk_forward_live_gate_from_klines(
        [], choppiness_max=Decimal("1.72")
    )
    assert r["ok"] is True
    assert r["side"] == "SELL"
    assert r["wf_gate_source"] == "grid_meets_target"
    assert r["tp_median_multiplier"] == "0.65"
    assert r["sl_median_multiplier"] == "0.65"
    snap = r.get("wf_variation_snapshot")
    assert isinstance(snap, dict)
    assert snap.get("resolved_tp_win_rate_pct") == "100.00"
    assert snap.get("rank") == 0


def test_build_coin_analysis_payload_includes_hold_window_settings() -> None:
    klines = [_synth_bar(i * 60_000, str(100 + (i % 5))) for i in range(90)]
    raw = {"data": [{"time": int(k["time"]), "open": str(k["open"]), "high": str(k["high"]), "low": str(k["low"]), "close": str(k["close"])} for k in klines]}
    hold = HoldWindowParams(enabled=True, min_minutes=30, max_minutes=35, step_minutes=5)
    payload = build_coin_analysis_payload(
        symbol="BTCUSDT",
        max_leverage=20,
        lookback_minutes=1440,
        interval="15m",
        kline_limit=96,
        klines_raw=raw,
        hold_params=hold,
    )
    assert payload["hold_window_optimization"]["enabled"] is True
    assert payload["hold_window_optimization"]["min_minutes"] == 30
    vars0 = payload["walk_forward_tpsl_variations"]["variations"]
    assert vars0
    assert "hold_window" in vars0[0]
