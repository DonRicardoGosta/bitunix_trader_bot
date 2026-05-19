"""candidate_backtest: :15 belépés és fix TP/SL variációk."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.services.candidate_backtest import (
    BACKTEST_ENTRY_MINUTE,
    entry_bar_indices,
    evaluate_symbol_variations,
    is_hour_quarter_entry_bar,
    simulate_variation_on_klines,
)


def _bar_at(minute: int, hour: int = 10, close: str = "100") -> dict[str, Decimal]:
    dt = datetime(2025, 1, 1, hour, minute, 0, tzinfo=UTC)
    ms = int(dt.timestamp() * 1000)
    c = Decimal(close)
    return {
        "time": Decimal(ms),
        "open": c,
        "high": c + Decimal("1"),
        "low": c - Decimal("1"),
        "close": c,
    }


def test_is_hour_quarter_entry_bar_only_15() -> None:
    assert is_hour_quarter_entry_bar(_bar_at(15))
    assert not is_hour_quarter_entry_bar(_bar_at(0))
    assert not is_hour_quarter_entry_bar(_bar_at(30))


def test_entry_bar_indices_filters_minute_15() -> None:
    klines: list[dict[str, Decimal]] = []
    for h in range(24):
        for m in (0, 15, 30, 45):
            klines.append(_bar_at(m, hour=h, close=str(100 + h)))
    idxs = entry_bar_indices(klines, minute=BACKTEST_ENTRY_MINUTE, min_train=15)
    assert len(idxs) > 0
    for i in idxs:
        assert is_hour_quarter_entry_bar(klines[i])


def test_simulate_only_tp_or_sl_closure() -> None:
    """Long: TP elérése egy gyertyán."""
    klines = []
    base_ms = int(datetime(2025, 1, 1, 0, 0, tzinfo=UTC).timestamp() * 1000)
    for i in range(40):
        m = 15 if i % 4 == 1 else 0
        h = i // 4
        dt = datetime(2025, 1, 1, h % 24, m, 0, tzinfo=UTC)
        ms = int(dt.timestamp() * 1000) + i * 60_000
        c = Decimal("100") + Decimal(i) * Decimal("0.01")
        klines.append(
            {
                "time": Decimal(ms),
                "open": c,
                "high": c + Decimal("5"),
                "low": c - Decimal("0.5"),
                "close": c,
            }
        )
    row = simulate_variation_on_klines(
        klines,
        tp_roi_pct=Decimal("50"),
        sl_roi_pct=Decimal("50"),
        leverage=20,
    )
    for t in row["trades"]:
        assert t["first_touch"] in ("tp", "sl", "none")


def test_evaluate_symbol_variations_insufficient_data() -> None:
    klines = [
        {
            "time": Decimal(i),
            "open": Decimal(1),
            "high": Decimal(1),
            "low": Decimal(1),
            "close": Decimal(1),
        }
        for i in range(10)
    ]
    out = evaluate_symbol_variations(klines)
    assert out["ok"] is False
    assert out["reason"] == "insufficient_klines"
