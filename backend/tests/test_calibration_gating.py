"""Trading gate: kalibráció hiányában a stratégia és a /orders endpoint
sem enged tradelni.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.base import Base
from app.db.models import (
    AuditEvent,
    AuditLevel,
    CalibrationStatus,
    Order,
    TpSlCalibration,
)
from app.db.session import AsyncSessionLocal, engine
from app.main import create_app
from app.services.strategy.base import StrategyContext
from app.services.strategy.top_movers import TopMoversStrategy


class FakeBitunixClient:
    def __init__(self) -> None:
        self.place_order_calls: list = []
        self.change_leverage_calls: list = []
        self.place_position_tp_sl_calls: list = []
        self._open_positions: dict[tuple[str, str], str] = {}

    async def get_all_tickers(self) -> dict:
        return {
            "data": [
                {
                    "symbol": "BBB",
                    "lastPrice": "60",
                    "open": "100",
                    "high": "100",
                    "low": "60",
                }
            ]
        }

    async def get_trading_pairs(self) -> dict:
        return {
            "data": [
                {
                    "symbol": "BBB",
                    "maxLeverage": "10",
                    "basePrecision": "2",
                    "pricePrecision": "2",
                }
            ]
        }

    async def get_account(self, margin_coin: str = "USDT") -> dict:
        return {"data": {"available": "1000"}}

    async def get_positions(self, symbol: str | None = None) -> dict:
        rows = []
        for (sym, side), pid in self._open_positions.items():
            if symbol and sym != symbol.upper():
                continue
            rows.append(
                {"symbol": sym, "side": side, "positionId": pid, "qty": "1"}
            )
        return {"data": rows} if rows else {"data": []}

    async def get_ticker(self, symbol: str) -> dict:
        return {"data": [{"symbol": symbol, "lastPrice": "60"}]}

    async def change_leverage(self, **kwargs) -> dict:
        self.change_leverage_calls.append(kwargs)
        return {"dryRun": True}

    async def place_order(self, **kwargs) -> dict:
        self.place_order_calls.append(kwargs)
        sym = str(kwargs.get("symbol", "")).upper()
        side = str(kwargs.get("side", "BUY")).upper()
        if kwargs.get("trade_side", "OPEN") == "OPEN" and not kwargs.get("reduce_only"):
            self._open_positions[(sym, side)] = f"pos-{sym}"
        return {"dryRun": True, "echo": kwargs}

    async def place_position_tp_sl_order(self, **kwargs) -> dict:
        self.place_position_tp_sl_calls.append(kwargs)
        return {"dryRun": True, "data": {"orderId": "tpsl"}, "echo": kwargs}


@pytest.fixture(scope="module", autouse=True)
def _create_schema() -> None:
    asyncio.run(_create_all())


async def _create_all() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_strategy_skips_when_no_calibration() -> None:
    """Friss kalibráció hiányában a top_movers nem ad fel rendelést."""
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(TpSlCalibration))
        await session.execute(sa.delete(Order))
        await session.execute(sa.delete(AuditEvent))
        await session.commit()

    fake = FakeBitunixClient()
    strategy = TopMoversStrategy()
    async with AsyncSessionLocal() as session:
        ctx = StrategyContext(
            session=session, client=fake, settings=get_settings(), triggered_by="test"
        )
        result = await strategy.run(ctx)
        await session.commit()

    assert result.placed_orders == []
    assert result.skipped == []
    assert result.details.get("reason") == "calibration_missing"
    assert fake.place_order_calls == []
    assert fake.change_leverage_calls == []

    async with AsyncSessionLocal() as session:
        warns = (
            await session.execute(
                sa.select(AuditEvent).where(
                    AuditEvent.event == "strategy.top_movers.calibration_missing"
                )
            )
        ).scalars().all()
        assert len(warns) == 1
        assert warns[0].level == AuditLevel.WARNING


@pytest.mark.asyncio
async def test_strategy_uses_per_symbol_calibration_when_available() -> None:
    """Sikeres kalibráció után a stratégia annak per-symbol értékeit használja."""
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(Order))
        await session.execute(sa.delete(TpSlCalibration))
        await session.execute(sa.delete(AuditEvent))
        summary = {
            "lookback_minutes": 120,
            "top_n": 20,
            "tp_atr_mult": "3.0",
            "sl_atr_mult": "1.5",
            "global": {
                "tp_move_pct": "1.0",
                "sl_move_pct": "0.5",
                "symbol_count": 1,
            },
            "per_symbol": {
                "BBB": {
                    "tp_move_pct": "2.0",
                    "sl_move_pct": "1.0",
                    "atr_pct": "0.66",
                    "samples": 120,
                    "last_close": "60",
                    "abs_change_24h_pct": "40",
                }
            },
            "failed_symbols": [],
        }
        session.add(
            TpSlCalibration(
                status=CalibrationStatus.SUCCESS,
                triggered_by="unit_test",
                lookback_minutes=120,
                top_n=20,
                summary=summary,
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            )
        )
        await session.commit()

    fake = FakeBitunixClient()
    strategy = TopMoversStrategy()
    async with AsyncSessionLocal() as session:
        ctx = StrategyContext(
            session=session, client=fake, settings=get_settings(), triggered_by="test"
        )
        result = await strategy.run(ctx)
        await session.commit()

    assert len(result.placed_orders) == 1
    placed = result.placed_orders[0]
    assert placed["symbol"] == "BBB"
    # Per-symbol 2%%/1%% — a stratégia a saját kalibrált értéket használja.
    # SHORT BBB entry=60: tp=59.40, sl=60.30 (round_up 2dec).
    assert placed["tp_source"] == "calibration_symbol"
    assert placed["tp_move_pct"] == "2.0"
    assert placed["sl_move_pct"] == "1.0"
    # SHORT BBB entry=60, TP 2%%, SL 1%% (per-symbol), 2 dec ROUND_UP
    assert Decimal(placed["tp_price"]) == Decimal("58.80")
    assert Decimal(placed["sl_price"]) == Decimal("60.60")
    assert result.details["calibration_used"] is True


def test_orders_endpoint_blocked_without_calibration() -> None:
    """A /api/orders POST 409-et ad ha nincs friss kalibráció."""

    async def _clear() -> None:
        async with AsyncSessionLocal() as session:
            await session.execute(sa.delete(TpSlCalibration))
            await session.commit()

    asyncio.run(_clear())

    app = create_app()
    with TestClient(app) as client:
        r = client.post(
            "/api/orders",
            json={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "orderType": "MARKET",
                "quantity": "0.01",
            },
        )
        assert r.status_code == 409
        assert "Trading zárolva" in r.json()["detail"]


def test_orders_endpoint_allowed_with_fresh_calibration() -> None:
    """Sikeres friss kalibráció után a /api/orders POST visszaengedi a tradelést."""

    async def _seed() -> None:
        async with AsyncSessionLocal() as session:
            await session.execute(sa.delete(TpSlCalibration))
            session.add(
                TpSlCalibration(
                    status=CalibrationStatus.SUCCESS,
                    triggered_by="unit_test",
                    lookback_minutes=120,
                    top_n=20,
                    summary={
                        "lookback_minutes": 120,
                        "top_n": 20,
                        "tp_atr_mult": "3.0",
                        "sl_atr_mult": "1.5",
                        "global": {"tp_move_pct": "1", "sl_move_pct": "0.5"},
                        "per_symbol": {},
                    },
                    started_at=datetime.now(UTC),
                    finished_at=datetime.now(UTC),
                )
            )
            await session.commit()

    asyncio.run(_seed())

    app = create_app()
    with TestClient(app) as client:
        r = client.post(
            "/api/orders",
            json={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "orderType": "MARKET",
                "quantity": "0.01",
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["dry_run"] is True
