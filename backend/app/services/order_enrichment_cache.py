"""Rendelés-enrichment cache: párhuzamos list + pnl-totals ne duplázza a Bitunix hívásokat."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

from app.config import get_settings


def enrichment_cache_key(
    *,
    lookback_hours: int | None,
    order_count: int,
    newest_created_at_iso: str | None,
    symbol: str | None,
) -> str:
    """Cache kulcs ugyanahhoz a DB lekérdezéshez."""
    sym = (symbol or "").upper() or "*"
    lb = str(lookback_hours) if lookback_hours is not None else "all"
    ts = newest_created_at_iso or "none"
    return f"{lb}:{sym}:{order_count}:{ts}"


class OrderEnrichmentCache:
    """TTL cache + egyidejű kérések összevonása (singleflight)."""

    def __init__(self, ttl_seconds: float = 60.0) -> None:
        self._ttl = max(1.0, ttl_seconds)
        self._lock = asyncio.Lock()
        self._rows: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._inflight: dict[str, asyncio.Task[list[dict[str, Any]]]] = {}

    async def get_or_fetch(
        self,
        key: str,
        fetcher: Callable[[], Awaitable[list[dict[str, Any]]]],
    ) -> list[dict[str, Any]]:
        async with self._lock:
            now = time.monotonic()
            hit = self._rows.get(key)
            if hit is not None and now - hit[0] < self._ttl:
                return hit[1]
            task = self._inflight.get(key)
            if task is None:
                task = asyncio.create_task(self._run_fetch(key, fetcher))
                self._inflight[key] = task
            else:
                pass

        try:
            return await task
        except Exception:
            async with self._lock:
                self._inflight.pop(key, None)
            raise

    async def _run_fetch(
        self,
        key: str,
        fetcher: Callable[[], Awaitable[list[dict[str, Any]]]],
    ) -> list[dict[str, Any]]:
        try:
            rows = await fetcher()
        finally:
            async with self._lock:
                self._inflight.pop(key, None)
        async with self._lock:
            self._rows[key] = (time.monotonic(), rows)
        return rows


_global_enrichment_cache: OrderEnrichmentCache | None = None


def get_order_enrichment_cache() -> OrderEnrichmentCache:
    global _global_enrichment_cache
    if _global_enrichment_cache is None:
        ttl = float(get_settings().orders_enrichment_cache_ttl_seconds)
        _global_enrichment_cache = OrderEnrichmentCache(ttl_seconds=ttl)
    return _global_enrichment_cache


def clear_order_enrichment_cache() -> None:
    """Tesztek / place_order után."""
    global _global_enrichment_cache
    if _global_enrichment_cache is not None:
        _global_enrichment_cache._rows.clear()
        _global_enrichment_cache._inflight.clear()
