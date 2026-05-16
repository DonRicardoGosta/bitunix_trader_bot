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


def position_open_time(position: dict[str, Any]) -> datetime | None:
    """Nyitás ideje — előny: opened_at (normalizált history)."""
    return parse_position_ts(position.get("opened_at"))


def position_event_time(position: dict[str, Any]) -> datetime | None:
    """Lezárás ideje — előny: closed_at, majd updated_at; nyitás csak utolsó esély."""
    for key in ("closed_at", "updated_at"):
        ts = parse_position_ts(position.get(key))
        if ts is not None:
            return ts
    return None


def trade_hold_duration_seconds(position: dict[str, Any]) -> int | None:
    """Pozíció nyitás–lezárás tartama másodpercben, ha mindkét idő ismert."""
    opened = position_open_time(position)
    closed = position_event_time(position)
    if opened is None or closed is None:
        return None
    if closed <= opened:
        return None
    return int((closed - opened).total_seconds())


def filter_positions_in_window(
    positions: list[dict[str, Any]], *, since: datetime, until: datetime
) -> list[dict[str, Any]]:
    """Csak [since, until] között lezárt pozíciók — ismeretlen időbélyeg kiesik."""
    since_u = since.astimezone(UTC) if since.tzinfo else since.replace(tzinfo=UTC)
    until_u = until.astimezone(UTC) if until.tzinfo else until.replace(tzinfo=UTC)
    out: list[dict[str, Any]] = []
    for p in positions:
        ts = position_event_time(p)
        if ts is not None and since_u <= ts <= until_u:
            out.append(p)
    return out


def filter_positions_in_lookback(
    positions: list[dict[str, Any]], *, lookback_hours: int
) -> list[dict[str, Any]]:
    """Csak az ablakon belüli pozíciók — ismeretlen időbélyeg kiesik."""
    until = datetime.now(UTC)
    since = until - timedelta(hours=max(1, lookback_hours))
    return filter_positions_in_window(positions, since=since, until=until)


def history_pages_for_lookback(lookback_hours: int) -> int:
    """Lapozás: rövid ablak kevesebb, hosszú több oldal."""
    if lookback_hours <= 24:
        return 3
    if lookback_hours <= 168:
        return 5
    return 8


def history_pages_for_span_hours(span_hours: float) -> int:
    return history_pages_for_lookback(max(1, int(span_hours) or 1))


async def fetch_closed_positions_in_window(
    client: BitunixClient,
    *,
    since: datetime,
    until: datetime,
    history_page_size: int = 100,
) -> tuple[list[dict[str, Any]], str | None]:
    """Bitunix history + szűrés explicit kezdet/vég között."""
    sync_error: str | None = None
    since_u = since.astimezone(UTC) if since.tzinfo else since.replace(tzinfo=UTC)
    until_u = until.astimezone(UTC) if until.tzinfo else until.replace(tzinfo=UTC)
    start_ms = int(since_u.timestamp() * 1000)
    end_ms = int(until_u.timestamp() * 1000)
    span_h = max(1 / 60, (until_u - since_u).total_seconds() / 3600)
    pages = history_pages_for_span_hours(span_h)
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

    return filter_positions_in_window(raw_all, since=since_u, until=until_u), sync_error


async def fetch_closed_positions_in_lookback(
    client: BitunixClient,
    *,
    lookback_hours: int,
    history_page_size: int = 100,
) -> tuple[list[dict[str, Any]], str | None]:
    """Bitunix history + szigorú szerveroldali szűrés az ablakra."""
    until = datetime.now(UTC)
    since = until - timedelta(hours=max(1, lookback_hours))
    return await fetch_closed_positions_in_window(
        client, since=since, until=until, history_page_size=history_page_size
    )
