"""Hold-window optimalizálás unit tesztek."""

from __future__ import annotations

from decimal import Decimal

from app.services.hold_window import (
    HoldWindowParams,
    effective_hold_grid_minutes,
    evaluate_hold_window_grid,
    is_good_profit,
    signed_profit_move_pct,
    simulate_trade_exit_with_hold,
)


def _bar(t_ms: int, o: str, h: str, l: str, c: str) -> dict:
    return {
        "time": t_ms,
        "open": Decimal(o),
        "high": Decimal(h),
        "low": Decimal(l),
        "close": Decimal(c),
    }


def test_signed_profit_move_pct_long_and_short() -> None:
    assert signed_profit_move_pct(
        entry=Decimal("100"), exit_price=Decimal("115"), side="long"
    ) == Decimal("15")
    assert signed_profit_move_pct(
        entry=Decimal("100"), exit_price=Decimal("85"), side="short"
    ) == Decimal("15")


def test_simulate_tp_before_hold_deadline() -> None:
    entry_ms = 1_000_000
    bars = [
        _bar(entry_ms + 60_000, "100", "120", "99", "110"),
    ]
    kind, profit, off, _ = simulate_trade_exit_with_hold(
        bars,
        entry_time_ms=entry_ms,
        entry=Decimal("100"),
        side="long",
        tp_move_pct=Decimal("15"),
        sl_move_pct=Decimal("10"),
        hold_minutes=30,
    )
    assert kind == "tp"
    assert profit == Decimal("15")
    assert off == 0


def test_simulate_time_exit_good_profit() -> None:
    entry_ms = 0
    bars = [
        _bar(31 * 60 * 1000, "100", "117", "99", "116"),
    ]
    kind, profit, _, _ = simulate_trade_exit_with_hold(
        bars,
        entry_time_ms=entry_ms,
        entry=Decimal("100"),
        side="long",
        tp_move_pct=Decimal("50"),
        sl_move_pct=Decimal("50"),
        hold_minutes=30,
    )
    assert kind == "time"
    assert profit == Decimal("16")
    assert is_good_profit(profit, threshold_pct=Decimal("15"))


def test_effective_hold_grid_filters_coarse_klines() -> None:
    params = HoldWindowParams(
        enabled=True,
        min_minutes=30,
        max_minutes=60,
        step_minutes=5,
    )
    assert effective_hold_grid_minutes(params, kline_bar_minutes=15) == [
        30,
        45,
        60,
    ]
    assert effective_hold_grid_minutes(params, kline_bar_minutes=5) == [
        30,
        35,
        40,
        45,
        50,
        55,
        60,
    ]


def test_hold_window_grid_tie_break_prefers_shorter_hold() -> None:
    entry_ms = 0
    klines = [
        _bar(0, "100", "100", "100", "100"),
        _bar(45 * 60 * 1000, "100", "120", "99", "116"),
    ]
    trades = [
        {
            "entry_bar_index": 0,
            "entry_time_ms": entry_ms,
            "entry_price": "100",
            "predicted_side": "long",
            "tp_move_pct": "50",
            "sl_move_pct": "50",
        }
    ]
    params = HoldWindowParams(
        enabled=True,
        min_minutes=30,
        max_minutes=60,
        step_minutes=15,
        profit_threshold_pct=Decimal("15"),
    )
    result = evaluate_hold_window_grid(
        klines, trades, params=params, kline_bar_minutes=15
    )
    assert result["best_hold_minutes"] == 30
    rates = {int(r["hold_minutes"]): r["good_rate_pct"] for r in result["rows"]}
    assert rates[30] == rates[45] == rates[60]


def test_hold_window_grid_picks_best_minutes() -> None:
    entry_ms = 0
    klines = [
        _bar(0, "100", "100", "100", "100"),
        _bar(35 * 60 * 1000, "100", "112", "99", "111"),
        _bar(61 * 60 * 1000, "100", "120", "99", "118"),
    ]
    trades = [
        {
            "entry_bar_index": 0,
            "entry_time_ms": entry_ms,
            "entry_price": "100",
            "predicted_side": "long",
            "tp_move_pct": "50",
            "sl_move_pct": "50",
        }
    ]
    params = HoldWindowParams(
        enabled=True,
        min_minutes=30,
        max_minutes=60,
        step_minutes=30,
        profit_threshold_pct=Decimal("15"),
    )
    result = evaluate_hold_window_grid(klines, trades, params=params)
    assert result["best_hold_minutes"] == 60
    assert Decimal(str(result["best_good_rate_pct"])) == Decimal("100.00")
    assert len(result["rows"]) == 2
