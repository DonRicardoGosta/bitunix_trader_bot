"""Hold-window optimalizálás unit tesztek."""

from __future__ import annotations

from decimal import Decimal

from app.services.hold_window import (
    HoldWindowParams,
    evaluate_hold_window_grid,
    forward_bars_after_entry_time,
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
        bar_duration_ms=60_000,
    )
    assert kind == "time"
    assert profit == Decimal("16")
    assert is_good_profit(profit, threshold_pct=Decimal("15"))


def test_hold_window_grid_evaluates_all_five_minute_steps() -> None:
    entry_ms = 0
    hold_klines = [
        _bar(i * 5 * 60 * 1000, "100", "100", "100", "100")
        for i in range(20)
    ]
    hold_klines[6] = _bar(30 * 60 * 1000, "100", "112", "99", "111")
    hold_klines[7] = _bar(35 * 60 * 1000, "100", "100", "99", "105")
    hold_klines[12] = _bar(60 * 60 * 1000, "100", "120", "99", "118")
    wf_klines = [_bar(0, "100", "100", "100", "100")]
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
        step_minutes=5,
        profit_threshold_pct=Decimal("15"),
    )
    result = evaluate_hold_window_grid(
        wf_klines,
        trades,
        params=params,
        hold_klines=hold_klines,
        hold_sim_interval="5m",
    )
    assert result["grid_minutes"] == [30, 35, 40, 45, 50, 55, 60]
    assert len(result["rows"]) == 7
    assert result["hold_sim_interval"] == "5m"


def test_hold_window_grid_tie_break_prefers_shorter_hold() -> None:
    entry_ms = 0
    hold_klines = [
        _bar(i * 5 * 60 * 1000, "100", "116", "99", "116")
        for i in range(14)
    ]
    wf_klines = [_bar(0, "100", "100", "100", "100")]
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
    )
    result = evaluate_hold_window_grid(
        wf_klines,
        trades,
        params=params,
        hold_klines=hold_klines,
    )
    assert result["best_hold_minutes"] == 30


def test_hold_window_grid_picks_best_minutes() -> None:
    entry_ms = 0
    hold_klines = [
        _bar(i * 5 * 60 * 1000, "100", "100", "100", "100")
        for i in range(14)
    ]
    hold_klines[7] = _bar(7 * 5 * 60 * 1000, "100", "112", "99", "111")
    hold_klines[12] = _bar(12 * 5 * 60 * 1000, "100", "120", "99", "118")
    wf_klines = [_bar(0, "100", "100", "100", "100")]
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
    result = evaluate_hold_window_grid(
        wf_klines,
        trades,
        params=params,
        hold_klines=hold_klines,
    )
    assert result["best_hold_minutes"] == 60
    assert Decimal(str(result["best_good_rate_pct"])) == Decimal("100.00")


def test_forward_bars_after_entry_time() -> None:
    klines = [_bar(i * 60_000, "1", "1", "1", "1") for i in range(5)]
    fwd = forward_bars_after_entry_time(klines, 120_000)
    assert len(fwd) == 2
    assert int(fwd[0]["time"]) == 180_000
