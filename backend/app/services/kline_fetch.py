"""Kline lekérés hold-window szimulációhoz (paginált, finom felbontás)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.bitunix.client import BitunixClient
from app.services.calibration import parse_klines

HOLD_SIM_INTERVAL = "5m"
HOLD_SIM_BAR_MINUTES = 5
_KLINE_MAX_LIMIT = 200


def hold_simulation_span_minutes(
    lookback_minutes: int,
    *,
    hold_max_minutes: int = 60,
) -> int:
    """Lookback + tartási buffer (perc)."""
    return max(5, int(lookback_minutes)) + max(0, int(hold_max_minutes))


def merge_klines_by_time(
    chunks: list[list[dict[str, Decimal]]],
) -> list[dict[str, Decimal]]:
    """Idő szerint egyesített, deduplikált gyertya lista."""
    by_time: dict[int, dict[str, Decimal]] = {}
    for part in chunks:
        for row in part:
            by_time[int(row["time"])] = row
    return [by_time[k] for k in sorted(by_time)]


async def fetch_hold_simulation_klines(
    client: BitunixClient,
    symbol: str,
    *,
    lookback_minutes: int,
    hold_max_minutes: int = 60,
    interval: str = HOLD_SIM_INTERVAL,
    bar_minutes: int = HOLD_SIM_BAR_MINUTES,
    end_time_ms: int | None = None,
) -> list[dict[str, Decimal]]:
    """5 perces gyertyák a teljes lookback + hold ablakra (több API hívás, ha kell).

    A Bitunix max. 200 gyertya / kérés; hosszú lookbacknél visszafelé lapozunk.
    """
    end_ms = (
        end_time_ms
        if end_time_ms is not None
        else int(datetime.now(UTC).timestamp() * 1000)
    )
    span_min = hold_simulation_span_minutes(
        lookback_minutes, hold_max_minutes=hold_max_minutes
    )
    start_ms = end_ms - span_min * 60_000
    bar_ms = max(1, int(bar_minutes)) * 60_000
    chunk_span_ms = _KLINE_MAX_LIMIT * bar_ms

    chunks: list[list[dict[str, Decimal]]] = []
    cursor_end = end_ms
    while cursor_end > start_ms:
        cursor_start = max(start_ms, cursor_end - chunk_span_ms + bar_ms)
        raw = await client.get_klines(
            symbol,
            interval=interval,
            limit=_KLINE_MAX_LIMIT,
            start_time_ms=cursor_start,
            end_time_ms=cursor_end,
        )
        parsed = parse_klines(raw)
        if parsed:
            chunks.append(parsed)
        if cursor_start <= start_ms:
            break
        cursor_end = cursor_start - bar_ms

    return merge_klines_by_time(chunks)
