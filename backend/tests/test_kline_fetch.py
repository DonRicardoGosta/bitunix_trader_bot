"""Paginált hold-szimulációs kline lekérés."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.kline_fetch import (
    HOLD_SIM_BAR_MINUTES,
    merge_klines_by_time,
    hold_simulation_span_minutes,
)
from app.services.kline_fetch import fetch_hold_simulation_klines


def test_hold_simulation_span_minutes() -> None:
    assert hold_simulation_span_minutes(1440, hold_max_minutes=60) == 1500


def test_merge_klines_by_time_dedupes() -> None:
    a = [{"time": Decimal(100), "open": Decimal(1), "high": Decimal(1), "low": Decimal(1), "close": Decimal(1)}]
    b = [{"time": Decimal(100), "open": Decimal(2), "high": Decimal(2), "low": Decimal(2), "close": Decimal(2)}]
    c = [{"time": Decimal(200), "open": Decimal(3), "high": Decimal(3), "low": Decimal(3), "close": Decimal(3)}]
    merged = merge_klines_by_time([a, b, c])
    assert len(merged) == 2
    assert int(merged[0]["time"]) == 100
    assert merged[0]["close"] == Decimal(2)


class _FakeClient:
    def __init__(self, pages: list[list[dict]]) -> None:
        self._pages = pages
        self.calls: list[dict] = []

    async def get_klines(self, symbol: str, **kwargs) -> dict:
        self.calls.append({"symbol": symbol, **kwargs})
        idx = len(self.calls) - 1
        if idx < len(self._pages):
            return {"data": self._pages[idx]}
        return {"data": []}


@pytest.mark.asyncio
async def test_fetch_hold_simulation_klines_paginates() -> None:
    bar_ms = HOLD_SIM_BAR_MINUTES * 60_000
    end_ms = 10_000_000
    span = hold_simulation_span_minutes(1440, hold_max_minutes=60)
    start_ms = end_ms - span * 60_000
    page1_start = end_ms - 200 * bar_ms + bar_ms
    rows1 = [
        {
            "time": page1_start + i * bar_ms,
            "open": "1",
            "high": "1",
            "low": "1",
            "close": "1",
        }
        for i in range(200)
    ]
    rows2 = [
        {
            "time": start_ms + i * bar_ms,
            "open": "1",
            "high": "1",
            "low": "1",
            "close": "1",
        }
        for i in range(20)
    ]
    client = _FakeClient([rows1, rows2])
    out = await fetch_hold_simulation_klines(
        client,
        "BTCUSDT",
        lookback_minutes=1440,
        hold_max_minutes=60,
        end_time_ms=end_ms,
    )
    assert len(client.calls) >= 2
    assert len(out) > 200
