"""TP/SL óránkénti aggregáció unit tesztek."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.analytics import _tp_sl_by_hour_of_day


def test_tp_sl_by_hour_aggregates_across_days_same_hour() -> None:
    base = datetime(2026, 5, 10, 14, 30, tzinfo=UTC)  # 16:30 Budapest (CEST)
    rows = [
        {
            "symbol": "A",
            "realized_pnl": "10",
            "closed_at": base.isoformat(),
        },
        {
            "symbol": "B",
            "realized_pnl": "-5",
            "closed_at": (base + timedelta(days=3)).isoformat(),
        },
        {
            "symbol": "C",
            "realized_pnl": "2",
            "closed_at": (base + timedelta(hours=1)).isoformat(),
        },
    ]
    out = _tp_sl_by_hour_of_day(rows)
    assert out["timezone"] == "Europe/Budapest"
    assert out["total_tp"] == 2
    assert out["total_sl"] == 1
    h16 = next(h for h in out["hours"] if h["hour"] == 16)
    assert h16["tp_count"] == 1
    assert h16["sl_count"] == 1
    h17 = next(h for h in out["hours"] if h["hour"] == 17)
    assert h17["tp_count"] == 1
    assert h17["sl_count"] == 0


def test_tp_sl_by_hour_skips_zero_pnl() -> None:
    rows = [
        {
            "symbol": "X",
            "realized_pnl": "0",
            "closed_at": datetime(2026, 5, 10, 12, 0, tzinfo=UTC).isoformat(),
        },
    ]
    out = _tp_sl_by_hour_of_day(rows)
    assert out["total_tp"] == 0
    assert out["total_sl"] == 0
