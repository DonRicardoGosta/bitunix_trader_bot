"""Trade tartam aggregáció unit tesztek."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.analytics import _trade_hold_duration_stats
from app.services.position_history import trade_hold_duration_seconds


def test_trade_hold_duration_seconds() -> None:
    opened = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    closed = opened + timedelta(hours=2, minutes=30)
    row = {
        "opened_at": opened.isoformat(),
        "closed_at": closed.isoformat(),
        "realized_pnl": "1",
    }
    assert trade_hold_duration_seconds(row) == 9000


def test_trade_hold_duration_stats_summary_and_buckets() -> None:
    base_open = datetime(2026, 5, 11, 7, 0, tzinfo=UTC)  # Monday, zárás ~10:00 Budapest
    rows = [
        {
            "realized_pnl": "10",
            "opened_at": base_open.isoformat(),
            "closed_at": (base_open + timedelta(hours=1)).isoformat(),
        },
        {
            "realized_pnl": "-5",
            "opened_at": base_open.isoformat(),
            "closed_at": (base_open + timedelta(hours=2)).isoformat(),
        },
        {
            "realized_pnl": "2",
            "opened_at": (base_open + timedelta(days=7)).isoformat(),
            "closed_at": (base_open + timedelta(days=7, hours=3)).isoformat(),
        },
    ]
    out = _trade_hold_duration_stats(rows)
    assert out["summary"]["wins"]["count"] == 2
    assert out["summary"]["wins"]["avg_duration_sec"] == 7200  # (3600+10800)/2
    assert out["summary"]["losses"]["count"] == 1
    assert out["summary"]["losses"]["avg_duration_sec"] == 7200
    mon = next(d for d in out["by_weekday"] if d["label"] == "Hétfő")
    assert mon["wins"]["count"] == 2
    assert mon["losses"]["count"] == 1
    assert sum(h["wins"]["count"] for h in out["by_hour"]) == 2
