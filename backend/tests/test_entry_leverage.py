"""Belépési leverage feloldás és sorrend (leverage → qty)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.services.calibration import CalibrationResult, SymbolCalibration
from app.services.strategy.top_signal_entries import resolve_entry_leverage
from app.services.trading_pairs_meta import PairMeta


def test_resolve_entry_leverage_uses_calibration_winner() -> None:
    meta = PairMeta(symbol="DOGEUSDT", max_leverage=75, base_precision=0, price_precision=4)
    cal = CalibrationResult(started_at=datetime.now(UTC))
    cal.per_symbol["DOGEUSDT"] = SymbolCalibration(
        symbol="DOGEUSDT",
        tp_move_pct=Decimal("1"),
        sl_move_pct=Decimal("1"),
        atr_pct=Decimal("0"),
        samples=10,
        last_close=Decimal("1"),
        abs_change_24h_pct=Decimal("5"),
        leverage=50,
        pair_max_leverage=75,
    )
    lev, pair_max, capped = resolve_entry_leverage("DOGEUSDT", meta, cal)
    assert lev == 50
    assert pair_max == 75
    assert capped is True


def test_resolve_entry_leverage_falls_back_to_pair_max() -> None:
    meta = PairMeta(symbol="BTCUSDT", max_leverage=100, base_precision=3, price_precision=2)
    lev, pair_max, capped = resolve_entry_leverage("BTCUSDT", meta, None)
    assert lev == 100
    assert pair_max == 100
    assert capped is False
