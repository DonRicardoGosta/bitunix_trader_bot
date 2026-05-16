"""position_history ablakszűrés."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.position_history import filter_positions_in_lookback


def test_filter_excludes_old_and_unknown_timestamps() -> None:
    now = datetime.now(UTC)
    recent = (now - timedelta(hours=2)).isoformat()
    old = (now - timedelta(days=10)).isoformat()
    rows = [
        {"symbol": "A", "updated_at": recent, "opened_at": None},
        {"symbol": "B", "updated_at": old, "opened_at": None},
        {"symbol": "C", "updated_at": None, "opened_at": None},
    ]
    out = filter_positions_in_lookback(rows, lookback_hours=6)
    assert len(out) == 1
    assert out[0]["symbol"] == "A"
