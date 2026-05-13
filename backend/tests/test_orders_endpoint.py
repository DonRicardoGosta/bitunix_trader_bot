"""Integrációs teszt a /api/orders végpontra.

Az in-memory SQLite séma elkészítéséhez ``create_all``-t használ – az élesben
Alembic migráció gondoskodik ugyanerről.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import engine
from app.main import create_app


@pytest.fixture(scope="module", autouse=True)
def _create_schema() -> None:
    """Sémát hoz létre az in-memory SQLite engine-en."""
    asyncio.run(_create_all())


async def _create_all() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def test_place_order_dry_run_via_http() -> None:
    app = create_app()
    with TestClient(app) as client:
        payload = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "orderType": "MARKET",
            "quantity": "0.01",
            "leverage": 5,
        }
        response = client.post("/api/orders", json=payload)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["dry_run"] is True
        assert body["status"] == "NEW"
        assert body["client_order_id"].startswith("bt-")

        listing = client.get("/api/orders")
        assert listing.status_code == 200
        rows = listing.json()
        assert any(r["client_order_id"] == body["client_order_id"] for r in rows)
        first = next(r for r in rows if r["client_order_id"] == body["client_order_id"])
        assert first["symbol"] == "BTCUSDT"
        assert first["side"] == "BUY"
        assert first["leverage"] == 5
