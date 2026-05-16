"""Analytics egyedi időablak feloldás."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.analytics_window import resolve_analytics_window


def test_resolve_preset_lookback() -> None:
    before = datetime.now(UTC)
    w = resolve_analytics_window(lookback_hours=24, window_start=None, window_end=None)
    assert w.custom is False
    assert w.end_live is False
    assert w.lookback_hours == 24
    assert w.until >= before
    assert (w.until - w.since).total_seconds() >= 23 * 3600


def test_resolve_custom_window_fixed_end() -> None:
    start = datetime(2026, 5, 1, 10, 30, tzinfo=UTC)
    end = datetime(2026, 5, 10, 18, 45, tzinfo=UTC)
    w = resolve_analytics_window(
        lookback_hours=None, window_start=start, window_end=end
    )
    assert w.custom is True
    assert w.end_live is False
    assert w.since == start
    assert w.until == end
    assert w.lookback_hours >= 200


def test_resolve_custom_start_only_end_is_now() -> None:
    start = datetime.now(UTC) - timedelta(hours=12)
    before = datetime.now(UTC)
    w = resolve_analytics_window(lookback_hours=None, window_start=start, window_end=None)
    assert w.custom is True
    assert w.end_live is True
    assert w.since == start
    assert w.until >= before
    assert w.until <= datetime.now(UTC) + timedelta(seconds=2)


def test_resolve_rejects_end_without_start() -> None:
    with pytest.raises(ValueError, match="window_start"):
        resolve_analytics_window(
            lookback_hours=None,
            window_start=None,
            window_end=datetime(2026, 5, 1, tzinfo=UTC),
        )


def test_resolve_rejects_inverted_range() -> None:
    start = datetime(2026, 5, 10, tzinfo=UTC)
    end = datetime(2026, 5, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="után"):
        resolve_analytics_window(
            lookback_hours=None, window_start=start, window_end=end
        )


def test_resolve_caps_end_to_now() -> None:
    future = datetime.now(UTC) + timedelta(days=1)
    start = datetime.now(UTC) - timedelta(hours=6)
    w = resolve_analytics_window(
        lookback_hours=None, window_start=start, window_end=future
    )
    assert w.end_live is False
    assert w.until <= datetime.now(UTC) + timedelta(seconds=2)
