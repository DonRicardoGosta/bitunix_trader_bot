"""entry_schedule: live :15/:20/:25 belépési ablak."""

from __future__ import annotations

from datetime import UTC, datetime

from app.services.entry_schedule import (
    LIVE_ENTRY_MINUTES,
    is_hour_quarter_entry_now,
    is_live_entry_window_now,
)


def test_live_entry_minutes_are_15_20_25() -> None:
    assert LIVE_ENTRY_MINUTES == (15, 20, 25)


def test_is_live_entry_window_now_15_20_25() -> None:
    assert is_live_entry_window_now(datetime(2025, 6, 1, 10, 15, 0, tzinfo=UTC))
    assert is_live_entry_window_now(datetime(2025, 6, 1, 10, 20, 0, tzinfo=UTC))
    assert is_live_entry_window_now(datetime(2025, 6, 1, 10, 25, 0, tzinfo=UTC))
    assert not is_live_entry_window_now(datetime(2025, 6, 1, 10, 14, 59, tzinfo=UTC))
    assert not is_live_entry_window_now(datetime(2025, 6, 1, 10, 16, 0, tzinfo=UTC))
    assert not is_live_entry_window_now(datetime(2025, 6, 1, 10, 30, 0, tzinfo=UTC))


def test_is_hour_quarter_entry_now_single_minute() -> None:
    assert is_hour_quarter_entry_now(datetime(2025, 6, 1, 10, 15, 0, tzinfo=UTC))
    assert not is_hour_quarter_entry_now(datetime(2025, 6, 1, 10, 20, 0, tzinfo=UTC))
