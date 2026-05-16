"""Lezárt pozíciók időablak szerinti szűrése és lekérése."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.bitunix.client import BitunixClient
from app.bitunix.exceptions import BitunixAPIError, BitunixSignatureError
from app.services.order_enrichment import extract_history_position_rows
from app.services.positions_normalize import normalize_position_row


def parse_position_ts(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return None


def position_event_time(position: dict[str, Any]) -> datetime | None:
    """Lezárás ideje (ha nincs, nyitás — utolsó esély)."""
    return parse_position_ts(position.get("updated_at")) or parse_position_ts(
        position.get("opened_at")
    )


def filter_positions_in_lookback(
    positions: list[dict[str, Any]], *, lookback_hours: int
) -> list[dict[str, Any]]:
    """Csak az ablakon belüli pozíciók — ismeretlen időbélyeg kiesik."""
    since = datetime.now(UTC) - timedelta(hours=max(1, lookback_hours))
    out: list[dict[str, Any]] = []
    for p in positions:
        ts = position_event_time(p)
        if ts is not None and ts >= since:
            out.append(p)
    return out


def history_pages_for_lookback(lookback_hours: int) -> int:
    """Lapozás: rövid ablak kevesebb, hosszú több oldal."""
    if lookback_hours <= 24:
        return 3
    if lookback_hours <= 168:
        return 5
    return 8


async def fetch_closed_positions_in_lookback(
    client: BitunixClient,
    *,
    lookback_hours: int,
    history_page_size: int = 100,
) -> tuple[list[dict[str, Any]], str | None]:
    """Bitunix history + szigorú szerveroldali szűrés az ablakra."""
    sync_error: str | None = None
    since = datetime.now(UTC) - timedelta(hours=max(1, lookback_hours))
    start_ms = int(since.timestamp() * 1000)
    end_ms = int(datetime.now(UTC).timestamp() * 1000)
    pages = history_pages_for_lookback(lookback_hours)
    raw_all: list[dict[str, Any]] = []

    for page in range(pages):
        try:
            raw_h = await client.get_history_positions(
                limit=history_page_size,
                skip=page * history_page_size,
                start_time_ms=start_ms,
                end_time_ms=end_ms,
            )
            rows = extract_history_position_rows(raw_h)
            if not rows:
                break
            for r in rows:
                raw_all.append(normalize_position_row(r))
            if len(rows) < history_page_size:
                break
        except (BitunixAPIError, BitunixSignatureError) as exc:
            sync_error = str(exc)[:500]
            break

    return filter_positions_in_lookback(raw_all, lookback_hours=lookback_hours), sync_error
