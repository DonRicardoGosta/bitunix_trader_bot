"""Kline lekérés hold-window szimulációhoz (paginált, finom felbontás)."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.bitunix.client import BitunixClient
from app.bitunix.exceptions import BitunixAPIError, BitunixSignatureError
from app.services.calibration import parse_klines

HOLD_SIM_INTERVAL = "5m"
HOLD_SIM_BAR_MINUTES = 5
_KLINE_MAX_LIMIT = 200

# Bitunix 10006 = request too frequently
_RATE_LIMIT_CODES = frozenset({"10006"})
_MAX_KLINE_RETRIES = 6
_MIN_KLINE_INTERVAL_SEC = 0.4
_PAGE_PAUSE_SEC = 0.25
_KLINE_CONCURRENCY = 2

_kline_sem = asyncio.Semaphore(_KLINE_CONCURRENCY)
_kline_pace_lock = asyncio.Lock()
_last_kline_at = 0.0


async def _pace_kline_request() -> None:
    """Globális minimum távolság két kline kérés között."""
    global _last_kline_at
    async with _kline_pace_lock:
        now = time.monotonic()
        wait = _MIN_KLINE_INTERVAL_SEC - (now - _last_kline_at)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_kline_at = time.monotonic()


def _is_rate_limit_error(exc: BaseException) -> bool:
    if isinstance(exc, BitunixAPIError) and exc.code in _RATE_LIMIT_CODES:
        return True
    msg = str(exc).lower()
    return "too frequently" in msg or "10006" in msg


async def get_klines_rate_limited(
    client: BitunixClient,
    symbol: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """``get_klines`` throttle + retry Bitunix rate limit (10006) esetén."""
    last_exc: BaseException | None = None
    for attempt in range(_MAX_KLINE_RETRIES):
        async with _kline_sem:
            await _pace_kline_request()
            try:
                return await client.get_klines(symbol, **kwargs)
            except (BitunixAPIError, BitunixSignatureError) as exc:
                last_exc = exc
                if _is_rate_limit_error(exc) and attempt < _MAX_KLINE_RETRIES - 1:
                    await asyncio.sleep(_MIN_KLINE_INTERVAL_SEC * (2**attempt))
                    continue
                raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("get_klines_rate_limited: unreachable")


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
    Kérésenként throttle és 10006 retry.
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
        raw = await get_klines_rate_limited(
            client,
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
        if cursor_end > start_ms:
            await asyncio.sleep(_PAGE_PAUSE_SEC)

    return merge_klines_by_time(chunks)


async def fetch_lookback_klines(
    client: BitunixClient,
    symbol: str,
    *,
    lookback_minutes: int,
    interval: str = "15m",
    bar_minutes: int = 15,
    end_time_ms: int | None = None,
) -> list[dict[str, Decimal]]:
    """Paginált gyertyák egy lookback ablakra (pl. 7 nap 15m)."""
    end_ms = (
        end_time_ms
        if end_time_ms is not None
        else int(datetime.now(UTC).timestamp() * 1000)
    )
    span_min = max(5, int(lookback_minutes))
    start_ms = end_ms - span_min * 60_000
    bar_ms = max(1, int(bar_minutes)) * 60_000
    chunk_span_ms = _KLINE_MAX_LIMIT * bar_ms

    chunks: list[list[dict[str, Decimal]]] = []
    cursor_end = end_ms
    while cursor_end > start_ms:
        cursor_start = max(start_ms, cursor_end - chunk_span_ms + bar_ms)
        raw = await get_klines_rate_limited(
            client,
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
        if cursor_end > start_ms:
            await asyncio.sleep(_PAGE_PAUSE_SEC)

    merged = merge_klines_by_time(chunks)
    return [k for k in merged if _to_int_ms(k["time"]) >= start_ms]


def _to_int_ms(time_val: Decimal) -> int:
    v = int(time_val)
    if v < 10**11:
        return v * 1000
    return v
