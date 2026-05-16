"""position_history ablakszűrés."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.position_history import (
    filter_positions_in_lookback,
    filter_positions_in_window,
)


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


def test_filter_positions_in_explicit_window() -> None:
    now = datetime.now(UTC)
    inside = (now - timedelta(hours=3)).isoformat()
    outside = (now - timedelta(hours=30)).isoformat()
    since = now - timedelta(hours=12)
    until = now - timedelta(hours=1)
    rows = [
        {"symbol": "A", "closed_at": inside},
        {"symbol": "B", "closed_at": outside},
    ]
    out = filter_positions_in_window(rows, since=since, until=until)
    assert len(out) == 1
    assert out[0]["symbol"] == "A"
