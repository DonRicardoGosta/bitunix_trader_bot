"""Stratégia config API tesztek."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.models import AppRuntimeSetting
from app.db.session import AsyncSessionLocal, engine
from app.main import create_app
import sqlalchemy as sa


def _schema() -> None:
    asyncio.run(_create_all())


async def _create_all() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _clear() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(AppRuntimeSetting))
        await session.commit()


def test_top_signal_entries_config_get_put() -> None:
    _schema()
    asyncio.run(_clear())
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/strategies/top_signal_entries/config")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["config"]["count"] == 10
        assert body["config"]["kline_lookahead"] == 1000
        assert body["enabled"] is True
        assert body["live_trading"] is True

        r2 = client.put(
            "/api/strategies/top_signal_entries/config",
            json={"count": 3, "wf_gate_enabled": False},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["config"]["count"] == 3
        assert r2.json()["config"]["wf_gate_enabled"] is False

        r3 = client.get("/api/strategies/top_signal_entries/config")
        assert r3.json()["config"]["count"] == 3
