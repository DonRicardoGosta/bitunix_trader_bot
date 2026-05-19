"""Óránkénti belépési időablak (live :15/:20, backtest kalibráció :15)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.services.candidate_backtest import BACKTEST_ENTRY_MINUTE

# Live trade: új pozíció csak ezekben az UTC percekben.
LIVE_ENTRY_MINUTES: tuple[int, ...] = (15, 20)


def is_live_entry_window_now(now: datetime | None = None) -> bool:
    """Igaz, ha az aktuális UTC perc engedélyezett live belépési ablak (:15 vagy :20)."""
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    else:
        now = now.astimezone(UTC)
    return now.minute in LIVE_ENTRY_MINUTES


def is_hour_quarter_entry_now(
    now: datetime | None = None,
    *,
    minute: int = BACKTEST_ENTRY_MINUTE,
) -> bool:
    """Egy adott perc ellenőrzése (backtest / legacy); live-hoz ``is_live_entry_window_now``."""
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    else:
        now = now.astimezone(UTC)
    return now.minute == minute
