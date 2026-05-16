"""TP/SL idő szerinti aggregáció unit tesztek."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.analytics import _tp_sl_timing_stats


def test_tp_sl_timing_aggregates_hour_and_weekday() -> None:
    base = datetime(2026, 5, 11, 14, 30, tzinfo=UTC)  # Monday 16:30 Budapest
    rows = [
        {
            "symbol": "A",
            "realized_pnl": "10",
            "closed_at": base.isoformat(),
        },
        {
            "symbol": "B",
            "realized_pnl": "-5",
            "closed_at": (base + timedelta(days=7)).isoformat(),
        },
        {
            "symbol": "C",
            "realized_pnl": "2",
            "closed_at": (base + timedelta(hours=1)).isoformat(),
        },
    ]
    out = _tp_sl_timing_stats(rows)
    assert out["timezone"] == "Europe/Budapest"
    assert out["total_tp"] == 2
    assert out["total_sl"] == 1
    assert len(out["by_hour"]) == 24
    assert len(out["by_weekday"]) == 7
    mon = next(d for d in out["by_weekday"] if d["label"] == "Hétfő")
    assert mon["tp_count"] == 2
    assert mon["sl_count"] == 1


def test_tp_sl_timing_skips_zero_pnl() -> None:
    rows = [
        {
            "symbol": "X",
            "realized_pnl": "0",
            "closed_at": datetime(2026, 5, 10, 12, 0, tzinfo=UTC).isoformat(),
        },
    ]
    out = _tp_sl_timing_stats(rows)
    assert out["total_tp"] == 0
    assert out["total_sl"] == 0
