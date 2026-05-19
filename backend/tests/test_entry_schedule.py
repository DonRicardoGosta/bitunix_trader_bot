"""entry_schedule: :15 belépési ablak."""

from __future__ import annotations

from datetime import UTC, datetime

from app.services.entry_schedule import is_hour_quarter_entry_now


def test_is_hour_quarter_entry_now_only_minute_15() -> None:
    assert is_hour_quarter_entry_now(datetime(2025, 6, 1, 10, 15, 0, tzinfo=UTC))
    assert not is_hour_quarter_entry_now(datetime(2025, 6, 1, 10, 14, 59, tzinfo=UTC))
    assert not is_hour_quarter_entry_now(datetime(2025, 6, 1, 10, 16, 0, tzinfo=UTC))
