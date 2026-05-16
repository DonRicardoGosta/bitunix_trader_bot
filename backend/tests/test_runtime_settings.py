"""Runtime settings és trading gate tesztek."""

from __future__ import annotations

import asyncio

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.models import AppRuntimeSetting
from app.db.session import AsyncSessionLocal, engine
from app.main import create_app
from app.services.runtime_settings import (
    apply_settings_patch,
    build_settings_snapshot,
    is_trading_paused,
)


@pytest.fixture(scope="module", autouse=True)
def _schema() -> None:
    asyncio.run(_create_all())


async def _create_all() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _clear_runtime() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(AppRuntimeSetting))
        await session.commit()


@pytest.mark.asyncio
async def test_trading_pause_roundtrip() -> None:
    await _clear_runtime()
    async with AsyncSessionLocal() as session:
        assert not await is_trading_paused(session)
        await apply_settings_patch(session, {"trading_paused": True})
        await session.commit()
    async with AsyncSessionLocal() as session:
        assert await is_trading_paused(session)
        snap = await build_settings_snapshot(session)
        assert snap["effective"]["trading_paused"] is True


def test_settings_api_get_and_patch() -> None:
    asyncio.run(_clear_runtime())
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/settings")
        assert r.status_code == 200
        assert "effective" in r.json()
        r2 = client.patch(
            "/api/settings",
            json={"trading_paused": True, "strategy_top_movers_enabled": False},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["applied"]["trading_paused"] is True
        r3 = client.post("/api/settings/trading-pause", json={"paused": False})
        assert r3.status_code == 200
        assert r3.json()["trading_paused"] is False


def test_analytics_pnl_series_structure() -> None:
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/analytics/pnl-series?lookback_hours=24&bucket_hours=6")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["lookback_hours"] == 24
        assert "buckets" in body
        assert "kpis" in body
        assert "window_start" in body
        assert "breakdown" in body


def test_analytics_summary_structure() -> None:
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/analytics/summary?lookback_hours=6&bucket_hours=1")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["lookback_hours"] == 6
        assert body["bucket_hours"] == 1
        assert "pnl" in body
        assert "orders" in body
        assert "strategy" in body
        assert body["pnl"]["lookback_hours"] == 6


def test_dashboard_lookback_hours() -> None:
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/dashboard/summary?lookback_hours=12")
        assert r.status_code == 200, r.text
        assert r.json()["lookback_hours"] == 12
