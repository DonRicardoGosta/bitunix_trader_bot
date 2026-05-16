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


def test_tp_sl_timing_weekday_hour_aggregates_same_weekday_instances() -> None:
    """Két külön hétfő ugyanabban az órában → egy bucketben összeadódik."""
    mon1 = datetime(2026, 5, 11, 8, 0, tzinfo=UTC)  # Hétfő 10:00 Budapest
    mon2 = datetime(2026, 5, 18, 8, 0, tzinfo=UTC)  # következő hétfő, ugyanaz az óra
    rows = [
        {"symbol": "A", "realized_pnl": "10", "closed_at": mon1.isoformat()},
        {"symbol": "B", "realized_pnl": "3", "closed_at": mon2.isoformat()},
        {
            "symbol": "C",
            "realized_pnl": "-1",
            "closed_at": (mon1 + timedelta(hours=2)).isoformat(),
        },
    ]
    out = _tp_sl_timing_stats(rows)
    mon_block = next(b for b in out["by_weekday_hour"] if b["weekday"] == 0)
    hour10 = next(h for h in mon_block["by_hour"] if h["hour"] == 10)
    hour12 = next(h for h in mon_block["by_hour"] if h["hour"] == 12)
    assert hour10["tp_count"] == 2
    assert hour10["sl_count"] == 0
    assert hour12["sl_count"] == 1


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
