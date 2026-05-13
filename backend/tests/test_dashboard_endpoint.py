"""HTTP integráció a /api/dashboard/summary végponthoz."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import engine
from app.main import create_app


@pytest.fixture(scope="module", autouse=True)
def _create_schema() -> None:
    asyncio.run(_create_all())


async def _create_all() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def test_dashboard_summary_returns_structure() -> None:
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/dashboard/summary?lookback_days=7")
        assert r.status_code == 200, r.text
        body = r.json()
        for key in ("orders", "events", "strategy", "exchange", "generated_at"):
            assert key in body
        assert body["lookback_days"] == 7
        # Az exchange ág akkor is megjön, ha nincs élő Bitunix kapcsolat
        assert "open_positions" in body["exchange"]
        assert "closed_positions" in body["exchange"]


def test_dashboard_summary_validates_lookback() -> None:
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/dashboard/summary?lookback_days=0")
        assert r.status_code == 422
        r = client.get("/api/dashboard/summary?lookback_days=200")
        assert r.status_code == 422
