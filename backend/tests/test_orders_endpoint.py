"""Integrációs teszt a /api/orders végpontra.

Az in-memory SQLite séma elkészítéséhez ``create_all``-t használ – az élesben
Alembic migráció gondoskodik ugyanerről.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.models import CalibrationStatus, TpSlCalibration
from app.db.session import AsyncSessionLocal, engine
from app.main import create_app


@pytest.fixture(scope="module", autouse=True)
def _create_schema() -> None:
    """Sémát hoz létre az in-memory SQLite engine-en."""
    asyncio.run(_create_all())


async def _create_all() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _seed_calibration() -> None:
    """Friss SUCCESS kalibráció, hogy a trading gate átengedjen."""
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(TpSlCalibration))
        session.add(
            TpSlCalibration(
                status=CalibrationStatus.SUCCESS,
                triggered_by="test_setup",
                lookback_minutes=120,
                top_n=20,
                summary={"global": {"tp_move_pct": "1", "sl_move_pct": "0.5"}},
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            )
        )
        await session.commit()


def test_place_order_dry_run_via_http() -> None:
    asyncio.run(_seed_calibration())
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
        raw = body.get("raw") or {}
        assert raw.get("tpsl_mode") == "position_full"
        pos_tpsl = raw.get("positionTpSl") or {}
        pos_echo = pos_tpsl.get("echo") or {}
        assert pos_echo.get("tpPrice") is not None
        assert pos_echo.get("slPrice") is not None
        assert pos_echo.get("positionId") is not None
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
        assert "exchange" in first
        assert "lifecycle" in first["exchange"]
        assert "lifecycle_label" in first["exchange"]
        assert "entry_context" in first
        assert first["entry_context"] is None

        dbg_list = client.get("/api/orders?debug_sync=true")
        assert dbg_list.status_code == 200
        dbg_row = next(r for r in dbg_list.json() if r["client_order_id"] == body["client_order_id"])
        assert "debug" in dbg_row["exchange"]
        assert dbg_row["exchange"]["debug"]["history_row_found"] is False


def test_list_orders_supports_pagination_and_symbol_filter() -> None:
    """``limit`` / ``offset`` / ``symbol`` paraméterek alapszintű ellenőrzése."""
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/orders?limit=1&offset=0")
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        assert len(rows) <= 1

        r = client.get("/api/orders?symbol=BTCUSDT&limit=10")
        assert r.status_code == 200
        rows = r.json()
        assert all(row["symbol"] == "BTCUSDT" for row in rows)

        # Túl nagy limit visszautasítva
        r_bad = client.get("/api/orders?limit=99999")
        assert r_bad.status_code == 422


def test_orders_pnl_totals_endpoint_shape() -> None:
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/orders/pnl-totals")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.keys() >= {
            "order_count",
            "realized_pnl_usdt",
            "unrealized_pnl_usdt",
            "total_pnl_usdt",
            "sync_error",
        }
        assert isinstance(body["order_count"], int)
