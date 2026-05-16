"""Analytics időablak feloldása (preset órák vagy egyedi kezdet + opcionális vég)."""

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
    end_live: bool = False


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _validate_custom_span(
    since: datetime, until: datetime, *, now: datetime
) -> tuple[datetime, int]:
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
    return until, max(1, int(span_h) or 1)


def resolve_analytics_window(
    *,
    lookback_hours: int | None,
    window_start: datetime | None,
    window_end: datetime | None,
) -> ResolvedAnalyticsWindow:
    """Preset lookback, vagy ``window_start`` (+ opcionális ``window_end``).

    Csak ``window_start``: a vége mindig a jelenlegi idő (élő / now).
    ``window_start`` + ``window_end``: fix tartomány (vég max. most).
  """
    now = datetime.now(UTC)
    has_start = window_start is not None
    has_end = window_end is not None

    if has_end and not has_start:
        raise ValueError("window_end nélkül window_start nem adható meg")

    if has_start:
        since = _ensure_utc(window_start)  # type: ignore[arg-type]
        if has_end:
            until = _ensure_utc(window_end)  # type: ignore[arg-type]
            until, equiv_h = _validate_custom_span(since, until, now=now)
            return ResolvedAnalyticsWindow(
                since=since,
                until=until,
                lookback_hours=equiv_h,
                custom=True,
                end_live=False,
            )
        until, equiv_h = _validate_custom_span(since, now, now=now)
        return ResolvedAnalyticsWindow(
            since=since,
            until=until,
            lookback_hours=equiv_h,
            custom=True,
            end_live=True,
        )

    hours = lookback_hours if lookback_hours is not None else 24
    hours = max(1, min(hours, MAX_WINDOW_HOURS))
    since = now - timedelta(hours=hours)
    return ResolvedAnalyticsWindow(
        since=since, until=now, lookback_hours=hours, custom=False, end_live=False
    )
