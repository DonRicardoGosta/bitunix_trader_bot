"""Order enrichment cache: TTL + singleflight."""

from __future__ import annotations

import asyncio

import pytest

from app.services.order_enrichment_cache import (
    OrderEnrichmentCache,
    clear_order_enrichment_cache,
    enrichment_cache_key,
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_order_enrichment_cache()
    yield
    clear_order_enrichment_cache()


@pytest.mark.asyncio
async def test_cache_returns_same_rows_within_ttl() -> None:
    cache = OrderEnrichmentCache(ttl_seconds=60.0)
    calls = 0

    async def fetcher() -> list[dict[str, object]]:
        nonlocal calls
        calls += 1
        return [{"id": calls}]

    rows1 = await cache.get_or_fetch("k1", fetcher)
    rows2 = await cache.get_or_fetch("k1", fetcher)
    assert rows1 == rows2 == [{"id": 1}]
    assert calls == 1


@pytest.mark.asyncio
async def test_singleflight_coalesces_parallel_fetches() -> None:
    cache = OrderEnrichmentCache(ttl_seconds=60.0)
    calls = 0
    started = asyncio.Event()

    async def fetcher() -> list[dict[str, object]]:
        nonlocal calls
        calls += 1
        started.set()
        await asyncio.sleep(0.05)
        return [{"n": calls}]

    t1 = asyncio.create_task(cache.get_or_fetch("parallel", fetcher))
    await started.wait()
    t2 = asyncio.create_task(cache.get_or_fetch("parallel", fetcher))
    r1, r2 = await asyncio.gather(t1, t2)
    assert r1 == r2 == [{"n": 1}]
    assert calls == 1


def test_enrichment_cache_key_stable() -> None:
    k1 = enrichment_cache_key(
        lookback_hours=6,
        order_count=3,
        newest_created_at_iso="2026-01-01T00:00:00+00:00",
        symbol=None,
    )
    k2 = enrichment_cache_key(
        lookback_hours=6,
        order_count=3,
        newest_created_at_iso="2026-01-01T00:00:00+00:00",
        symbol=None,
    )
    assert k1 == k2
    assert enrichment_cache_key(
        lookback_hours=6,
        order_count=3,
        newest_created_at_iso="2026-01-01T00:00:00+00:00",
        symbol="btcusdt",
    ) != k1
