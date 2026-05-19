"""Óránkénti belépési időablak (live + backtest :15)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.services.candidate_backtest import BACKTEST_ENTRY_MINUTE

LIVE_ENTRY_MINUTE = BACKTEST_ENTRY_MINUTE


def is_hour_quarter_entry_now(
    now: datetime | None = None,
    *,
    minute: int = LIVE_ENTRY_MINUTE,
) -> bool:
    """Igaz, ha az aktuális UTC perc a megadott óránkénti belépési perc (alap: :15)."""
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    else:
        now = now.astimezone(UTC)
    return now.minute == minute
