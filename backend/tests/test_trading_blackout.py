"""Trading blackout ütemezés unit tesztek."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.services.trading_blackout import (
    DayBlackoutConfig,
    TradingBlackoutSchedule,
    BlackoutTimeRange,
    is_in_trading_blackout,
    blackout_block_message,
)


def _schedule(**day_modes: tuple[str, list[tuple[str, str]] | None]) -> TradingBlackoutSchedule:
    days: dict[str, DayBlackoutConfig] = {}
    for key in (
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ):
        days[key] = DayBlackoutConfig()
    for key, spec in day_modes.items():
        mode, ranges = spec
        if mode == "open":
            days[key] = DayBlackoutConfig(mode="open")
        elif mode == "block_all":
            days[key] = DayBlackoutConfig(mode="block_all")
        else:
            days[key] = DayBlackoutConfig(
                mode="block_ranges",
                block_ranges=[
                    BlackoutTimeRange(start=a, end=b) for a, b in (ranges or [])
                ],
            )
    return TradingBlackoutSchedule(days=days)


def test_block_all_day() -> None:
    sched = _schedule(monday=("block_all", None))
    tz = ZoneInfo("Europe/Budapest")
    # 2026-05-11 is Monday
    at = datetime(2026, 5, 11, 12, 0, tzinfo=tz)
    assert is_in_trading_blackout(sched, at) is True
    assert "Hétfő" in (blackout_block_message(sched, at) or "")


def test_block_overnight_range() -> None:
    sched = _schedule(
        friday=(
            "block_ranges",
            [("22:00", "06:00")],
        ),
    )
    tz = ZoneInfo("Europe/Budapest")
    # Friday 2026-05-15 23:00 blocked
    at_night = datetime(2026, 5, 15, 23, 0, tzinfo=tz)
    assert is_in_trading_blackout(sched, at_night) is True
    # Friday 12:00 open
    at_day = datetime(2026, 5, 15, 12, 0, tzinfo=tz)
    assert is_in_trading_blackout(sched, at_day) is False


def test_open_day_default() -> None:
    sched = TradingBlackoutSchedule()
    at = datetime(2026, 5, 16, 10, 0, tzinfo=UTC)
    assert is_in_trading_blackout(sched, at) is False
