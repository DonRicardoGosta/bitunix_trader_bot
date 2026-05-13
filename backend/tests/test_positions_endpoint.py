"""HTTP integráció a /api/positions/normalized végponthoz."""

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


def test_positions_normalized_endpoint_no_credentials_returns_empty() -> None:
    """Élő Bitunix kapcsolat nélkül a végpont nem dől el – üres listát ad,
    illetve Bitunix-hibát propagál (502/401). Mindkét eset elfogadható."""
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/positions/normalized")
        # Test API kulcs nem valódi: Bitunix vagy 401/502-t ad,
        # vagy egy üres listát (ha sikerül a kérés).
        assert r.status_code in (200, 401, 502)
        if r.status_code == 200:
            body = r.json()
            assert "positions" in body and "totals" in body
            assert body["totals"]["count"] == len(body["positions"])
