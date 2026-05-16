"""Analytics időablak feloldása (preset órák vagy egyedi kezdet/vég)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

MAX_WINDOW_HOURS = 2160
MIN_WINDOW_SECONDS = 60


@dataclass(frozen=True)
class ResolvedAnalyticsWindow:
    since: datetime
    until: datetime
    lookback_hours: int
    custom: bool


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def resolve_analytics_window(
    *,
    lookback_hours: int | None,
    window_start: datetime | None,
    window_end: datetime | None,
) -> ResolvedAnalyticsWindow:
    """Preset lookback VAGY explicit ``window_start`` + ``window_end`` (együtt)."""
    now = datetime.now(UTC)
    has_start = window_start is not None
    has_end = window_end is not None
    if has_start != has_end:
        raise ValueError("window_start és window_end együtt kötelező")

    if has_start and has_end:
        since = _ensure_utc(window_start)  # type: ignore[arg-type]
        until = _ensure_utc(window_end)  # type: ignore[arg-type]
        if until > now:
            until = now
        if until <= since:
            raise ValueError("A vége időpont legyen a kezdet után")
        span_sec = (until - since).total_seconds()
        if span_sec < MIN_WINDOW_SECONDS:
            raise ValueError("Minimum 1 perc hosszú ablak")
        span_h = span_sec / 3600
        if span_h > MAX_WINDOW_HOURS:
            raise ValueError(f"Maximum {MAX_WINDOW_HOURS} óra (90 nap) hosszú ablak")
        equiv_h = max(1, int(span_h) or 1)
        return ResolvedAnalyticsWindow(
            since=since, until=until, lookback_hours=equiv_h, custom=True
        )

    hours = lookback_hours if lookback_hours is not None else 24
    hours = max(1, min(hours, MAX_WINDOW_HOURS))
    since = now - timedelta(hours=hours)
    return ResolvedAnalyticsWindow(
        since=since, until=now, lookback_hours=hours, custom=False
    )
