"""Kalibrációs matematika tesztek (ATR, TR, ranking, TP/SL move price)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.services.calibration import (
    CalibrationResult,
    SymbolCalibration,
    compute_atr_pct,
    compute_calibration_for_symbol,
    parse_klines,
    rank_top_symbols,
)
from app.services.tpsl import compute_tp_sl_prices_from_move_pct


def test_parse_klines_sorts_ascending_by_time() -> None:
    raw = {
        "data": [
            {"open": 1, "high": 2, "low": 0.5, "close": 1.5, "time": 200},
            {"open": 2, "high": 3, "low": 1, "close": 2, "time": 100},
            {"open": 2, "high": 3, "low": 1, "close": 2, "time": 300},
        ]
    }
    klines = parse_klines(raw)
    assert [int(k["time"]) for k in klines] == [100, 200, 300]


def test_parse_klines_drops_invalid_rows() -> None:
    raw = {
        "data": [
            {"open": 1, "high": 2, "low": 0.5, "close": 1.5, "time": 1},
            {"open": 1, "high": 2, "low": 0.5, "close": 0, "time": 2},  # zero close
            {"open": "x", "high": "y", "low": "z", "close": "0", "time": 3},
        ]
    }
    klines = parse_klines(raw)
    assert len(klines) == 1


def test_compute_atr_pct_known_value() -> None:
    """Két perces gyertya: TR = max(2-1, |2-1.5|, |1-1.5|) = 1.0, close=2 → 50%."""
    klines = [
        {"open": Decimal("1"), "high": Decimal("1.6"), "low": Decimal("1.4"), "close": Decimal("1.5"), "time": Decimal(0)},
        {"open": Decimal("1.5"), "high": Decimal("2"), "low": Decimal("1"), "close": Decimal("2"), "time": Decimal(1)},
    ]
    atr = compute_atr_pct(klines)
    assert atr is not None
    assert atr == Decimal("50")


def test_compute_atr_pct_returns_none_for_too_few() -> None:
    assert compute_atr_pct([]) is None
    assert compute_atr_pct([{"open": Decimal("1"), "high": Decimal("1"), "low": Decimal("1"), "close": Decimal("1"), "time": Decimal(0)}]) is None


def test_compute_calibration_for_symbol_no_clamp_extreme_atr() -> None:
    """Extrém ATR → nyers TP/SL (nincs plafon)."""
    raw = {
        "data": [
            {"open": 1, "high": 10, "low": 1, "close": 1, "time": 0},
            {"open": 1, "high": 10, "low": 1, "close": 1, "time": 1},
        ]
    }
    cal = compute_calibration_for_symbol(
        "X",
        raw,
        tp_atr_mult=Decimal("3"),
        sl_atr_mult=Decimal("1.5"),
        abs_change_24h_pct=Decimal("5"),
    )
    assert cal is not None
    assert cal.tp_move_pct == cal.atr_pct * Decimal("3")
    assert cal.sl_move_pct == cal.atr_pct * Decimal("1.5")
    assert cal.tp_move_pct > Decimal("10")


def test_compute_calibration_for_symbol_typical_values() -> None:
    """Reális ATR ~ 0.3% → TP=0.9%, SL=0.45%."""
    klines_raw = {"data": []}
    prev_close = Decimal("100")
    for i, (h, low, c) in enumerate(
        [
            (Decimal("100.3"), Decimal("99.7"), Decimal("100.1")),
            (Decimal("100.4"), Decimal("99.8"), Decimal("100.2")),
            (Decimal("100.5"), Decimal("99.9"), Decimal("100.3")),
            (Decimal("100.6"), Decimal("100.0"), Decimal("100.4")),
        ]
    ):
        klines_raw["data"].append(
            {"open": prev_close, "high": h, "low": low, "close": c, "time": i}
        )
        prev_close = c

    cal = compute_calibration_for_symbol(
        "X",
        klines_raw,
        tp_atr_mult=Decimal("3"),
        sl_atr_mult=Decimal("1.5"),
        abs_change_24h_pct=Decimal("5"),
    )
    assert cal is not None
    assert cal.tp_move_pct > Decimal("0.5")
    assert cal.sl_move_pct > Decimal("0.2")
    assert cal.tp_move_pct == cal.atr_pct * Decimal("3")
    assert cal.sl_move_pct == cal.atr_pct * Decimal("1.5")


def test_rank_top_symbols_ordered_by_abs_change() -> None:
    raw = {
        "data": [
            {"symbol": "AAA", "lastPrice": "110", "open": "100"},
            {"symbol": "BBB", "lastPrice": "60", "open": "100"},
            {"symbol": "CCC", "lastPrice": "125", "open": "100"},
            {"symbol": "DDD", "lastPrice": "100", "open": "100"},
        ]
    }
    ranked = rank_top_symbols(raw, top_n=3)
    syms = [s for s, _ in ranked]
    assert syms == ["BBB", "CCC", "AAA"]


def test_compute_tp_sl_prices_from_move_pct_long_and_short() -> None:
    """100 entry, +1% TP, -0.5% SL."""
    tp_l, sl_l = compute_tp_sl_prices_from_move_pct(
        entry_price=Decimal("100"),
        side="BUY",
        tp_move_pct=Decimal("1"),
        sl_move_pct=Decimal("0.5"),
        price_precision=2,
    )
    assert tp_l == Decimal("101.00")
    assert sl_l == Decimal("99.50")

    tp_s, sl_s = compute_tp_sl_prices_from_move_pct(
        entry_price=Decimal("100"),
        side="SELL",
        tp_move_pct=Decimal("1"),
        sl_move_pct=Decimal("0.5"),
        price_precision=2,
    )
    assert tp_s == Decimal("99.00")
    assert sl_s == Decimal("100.50")


def test_calibration_lookup_per_symbol_or_global_median() -> None:
    """Per-symbol saját érték; ismeretlen szimbólum → globál medián."""
    r = CalibrationResult(started_at=datetime.now(UTC))
    r.global_tp_move_pct = Decimal("2")
    r.global_sl_move_pct = Decimal("1")
    r.per_symbol["X"] = SymbolCalibration(
        symbol="X",
        tp_move_pct=Decimal("3"),
        sl_move_pct=Decimal("0.4"),
        atr_pct=Decimal("1"),
        samples=10,
        last_close=Decimal("100"),
        abs_change_24h_pct=Decimal("5"),
    )
    assert r.lookup("X") == (Decimal("3"), Decimal("0.4"))
    assert r.lookup("UNKNOWN") == (Decimal("2"), Decimal("1"))
