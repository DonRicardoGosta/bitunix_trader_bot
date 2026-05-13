"""Integrációs tesztek a ``services.dashboard`` modulhoz.

Az in-memory SQLite-on néhány Order + AuditEvent + StrategyRun seed-elve,
fake Bitunix klienssel az exchange-szinkron ág is végigfut.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa

from app.db.base import Base
from app.db.models import (
    AuditEvent,
    AuditLevel,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    StrategyRun,
    StrategyRunStatus,
)
from app.db.session import AsyncSessionLocal, engine
from app.services.dashboard import build_dashboard_summary


@pytest.fixture(scope="module", autouse=True)
def _create_schema() -> None:
    asyncio.run(_create_all())


async def _create_all() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _wipe() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(Order))
        await session.execute(sa.delete(AuditEvent))
        await session.execute(sa.delete(StrategyRun))
        await session.commit()


class _FakeClient:
    """Bitunix kliens mock dashboard tesztekhez."""

    def __init__(
        self,
        *,
        positions: list[dict[str, Any]] | None = None,
        history_positions: list[list[dict[str, Any]]] | None = None,
        account: dict[str, Any] | None = None,
        fail_account: bool = False,
    ) -> None:
        self._positions = positions or []
        self._history_pages = history_positions or [[]]
        self._account = account
        self._fail_account = fail_account

    async def get_account(self, margin_coin: str = "USDT") -> dict[str, Any]:
        if self._fail_account:
            from app.bitunix.exceptions import BitunixAPIError
            raise BitunixAPIError("auth", path="/account")
        return {"code": 0, "data": self._account or {}}

    async def get_positions(self, symbol: str | None = None) -> dict[str, Any]:
        return {"code": 0, "data": list(self._positions)}

    async def get_history_positions(
        self,
        *,
        symbol: str | None = None,
        limit: int = 100,
        skip: int = 0,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        position_id: str | None = None,
    ) -> dict[str, Any]:
        page_idx = skip // max(1, limit)
        rows = (
            self._history_pages[page_idx]
            if page_idx < len(self._history_pages)
            else []
        )
        return {
            "code": 0,
            "data": {"total": str(len(rows)), "positionList": list(rows)},
        }


@pytest.mark.asyncio
async def test_dashboard_aggregates_db_orders_and_events() -> None:
    await _wipe()
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        for i in range(3):
            o = Order(
                client_order_id=f"bt-test-{i}",
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                quantity=Decimal("1"),
                price=Decimal("60000"),
                leverage=10,
                status=OrderStatus.NEW,
            )
            session.add(o)
            await session.flush()
            o.created_at = now - timedelta(hours=i)
        session.add(
            Order(
                client_order_id="bt-eth-old",
                symbol="ETHUSDT",
                side=OrderSide.SELL,
                type=OrderType.MARKET,
                quantity=Decimal("1"),
                price=Decimal("3000"),
                leverage=5,
                status=OrderStatus.FILLED,
            )
        )
        session.add(
            AuditEvent(
                level=AuditLevel.ERROR,
                event="strategy.failed",
                message="API call failed",
            )
        )
        session.add(
            AuditEvent(level=AuditLevel.INFO, event="app.startup", message="ok")
        )
        session.add(
            StrategyRun(
                strategy_name="top_movers",
                status=StrategyRunStatus.SUCCESS,
                triggered_by="scheduler",
                started_at=now - timedelta(minutes=5),
            )
        )
        await session.commit()

    out = await build_dashboard_summary(session=session, client=None)
    assert out["orders"]["total"] == 4
    assert out["orders"]["last_24h"] >= 3
    assert any(
        s["symbol"] == "BTCUSDT" for s in out["orders"]["top_symbols_30d"]
    )
    assert out["events"]["total_24h"] >= 2
    assert "ERROR" in out["events"]["by_level_24h"]
    assert out["strategy"]["by_status_24h"].get("SUCCESS") == 1
    assert out["strategy"]["last_success"] is not None
    # Bitunix nélküli ág: sync_error a kulcs hiányára utal
    assert "kulcs" in out["exchange"]["sync_error"].lower()


@pytest.mark.asyncio
async def test_dashboard_exchange_summary_with_fake_client() -> None:
    await _wipe()

    open_positions = [
        {
            "positionId": "open-1",
            "symbol": "BTCUSDT",
            "qty": "1",
            "side": "BUY",
            "leverage": 10,
            "ctime": str(int(datetime.now(UTC).timestamp() * 1000)),
            "avgOpenPrice": "60000",
            "markPrice": "61000",
            "margin": "6000",
            "realizedPNL": "-1",
            "unrealizedPNL": "1000",
        }
    ]
    closed_page1 = [
        {
            "positionId": "p-win-1",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "maxQty": "1",
            "leverage": "10",
            "entryPrice": "60000",
            "closePrice": "60500",
            "realizedPNL": "500",
            "ctime": str(int(datetime.now(UTC).timestamp() * 1000) - 3600_000),
        },
        {
            "positionId": "p-loss-1",
            "symbol": "ETHUSDT",
            "side": "SELL",
            "maxQty": "10",
            "leverage": "10",
            "entryPrice": "3000",
            "closePrice": "3050",
            "realizedPNL": "-500",
            "ctime": str(int(datetime.now(UTC).timestamp() * 1000) - 7200_000),
        },
        {
            "positionId": "p-win-2",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "maxQty": "0.5",
            "leverage": "20",
            "entryPrice": "61000",
            "closePrice": "60500",
            "realizedPNL": "250",
            "ctime": str(int(datetime.now(UTC).timestamp() * 1000) - 1800_000),
        },
    ]
    fake = _FakeClient(
        positions=open_positions,
        account={
            "marginCoin": "USDT",
            "available": "1000",
            "margin": "6000",
            "crossUnrealizedPNL": "1000",
            "isolationUnrealizedPNL": "0",
            "bonus": "0",
            "positionMode": "HEDGE",
        },
        history_positions=[closed_page1],
    )
    async with AsyncSessionLocal() as session:
        out = await build_dashboard_summary(session=session, client=fake)  # type: ignore[arg-type]
    ex = out["exchange"]
    assert ex["sync_error"] is None
    assert ex["account"]["available"] == "1000"
    assert ex["open_positions"]["count"] == 1
    assert Decimal(ex["open_positions"]["total_unrealized_pnl_usdt"]) == Decimal("1000")
    assert Decimal(ex["open_positions"]["total_margin_usdt"]) == Decimal("6000")
    cp = ex["closed_positions"]
    assert cp["count"] == 3
    assert Decimal(cp["realized_pnl_usdt"]) == Decimal("250")
    assert cp["wins"] == 2
    assert cp["losses"] == 1
    # Win rate = 2/3 = 66.67
    assert cp["win_rate_pct"] == "66.67"
    assert cp["top_winners"][0]["realized_pnl"] == "500"
    assert cp["top_losers"][0]["realized_pnl"] == "-500"
    # per_symbol: BTCUSDT összesen +750, ETHUSDT -500
    by_sym = {row["symbol"]: row["realized_pnl_usdt"] for row in cp["per_symbol"]}
    assert Decimal(by_sym["BTCUSDT"]) == Decimal("750")
    assert Decimal(by_sym["ETHUSDT"]) == Decimal("-500")


@pytest.mark.asyncio
async def test_dashboard_handles_account_failure_gracefully() -> None:
    await _wipe()
    fake = _FakeClient(fail_account=True)
    async with AsyncSessionLocal() as session:
        out = await build_dashboard_summary(session=session, client=fake)  # type: ignore[arg-type]
    ex = out["exchange"]
    assert ex["sync_error"] is not None and "account" in ex["sync_error"].lower()
    # Az adatbázis-alapú aggregátum továbbra is jön
    assert "orders" in out and out["orders"]["total"] == 0
