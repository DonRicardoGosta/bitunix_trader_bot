"""Top movers stratégia end-to-end integráció (in-memory sqlite + fake kliens).

A Bitunix klienst egy ``FakeBitunixClient`` helyettesíti, amely előre megadott
válaszokat ad. Így a teljes ``TopMoversStrategy.run`` lefuttatható DB-vel,
és tudjuk ellenőrizni az audit eseményeket, a cooldownt és a kerekítést.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.config import get_settings
from app.db.base import Base
from app.db.models import (
    AuditEvent,
    AuditLevel,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
)
from app.db.session import AsyncSessionLocal, engine
from app.services.strategy.base import StrategyContext
from app.services.strategy.top_movers import TopMoversStrategy


class FakeBitunixClient:
    """Minimális, deterministic kliens-mock a stratégia teszteléséhez."""

    def __init__(
        self,
        *,
        tickers: dict,
        trading_pairs: dict,
        account: dict,
        change_leverage_response: dict | None = None,
        place_order_response: dict | None = None,
    ) -> None:
        self._tickers = tickers
        self._trading_pairs = trading_pairs
        self._account = account
        self._change_leverage_response = change_leverage_response or {"dryRun": True}
        self._place_order_response = place_order_response or {
            "dryRun": True,
            "echo": {},
        }
        self.change_leverage_calls: list[dict] = []
        self.place_order_calls: list[dict] = []

    async def get_all_tickers(self) -> dict:
        return self._tickers

    async def get_trading_pairs(self) -> dict:
        return self._trading_pairs

    async def get_account(self, margin_coin: str = "USDT") -> dict:
        return self._account

    async def change_leverage(
        self, *, symbol: str, leverage: int, margin_coin: str = "USDT"
    ) -> dict:
        self.change_leverage_calls.append(
            {"symbol": symbol, "leverage": leverage, "margin_coin": margin_coin}
        )
        return self._change_leverage_response

    async def place_order(self, **kwargs) -> dict:
        self.place_order_calls.append(kwargs)
        return self._place_order_response


@pytest.fixture(scope="module", autouse=True)
def _create_schema() -> None:
    asyncio.run(_create_all())


async def _create_all() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _make_tickers() -> dict:
    return {
        "data": [
            {"symbol": "AAA", "lastPrice": "110", "open": "100"},  # +10%
            {"symbol": "BBB", "lastPrice": "60", "open": "100"},  # -40% (top)
            {"symbol": "CCC", "lastPrice": "125", "open": "100"},  # +25% (#2)
            {"symbol": "DDD", "lastPrice": "85", "open": "100"},  # -15% (#3)
            {"symbol": "EEE", "lastPrice": "101", "open": "100"},  # +1%
        ]
    }


def _make_pairs() -> dict:
    return {
        "data": [
            {"symbol": "AAA", "maxLeverage": "50", "basePrecision": "3"},
            {"symbol": "BBB", "maxLeverage": "75", "basePrecision": "2"},
            {"symbol": "CCC", "maxLeverage": "100", "basePrecision": "4"},
            {"symbol": "DDD", "maxLeverage": "20", "basePrecision": "1"},
        ]
    }


@pytest.mark.asyncio
async def test_top_movers_places_orders_for_top3_with_correct_direction() -> None:
    """Top3 absolute mover → három rendelés, irány a mozgás előjelével."""
    fake = FakeBitunixClient(
        tickers=_make_tickers(),
        trading_pairs=_make_pairs(),
        account={"data": {"available": "1000"}},  # 1000 USDT → 1% = 10 USDT margin
    )
    settings = get_settings()
    strategy = TopMoversStrategy()
    async with AsyncSessionLocal() as session:
        ctx = StrategyContext(
            session=session, client=fake, settings=settings, triggered_by="test"
        )
        result = await strategy.run(ctx)
        await session.commit()

    placed = {o["symbol"]: o for o in result.placed_orders}
    assert set(placed.keys()) == {"BBB", "CCC", "DDD"}
    assert placed["BBB"]["side"] == "SELL"  # -40% → short
    assert placed["CCC"]["side"] == "BUY"   # +25% → long
    assert placed["DDD"]["side"] == "SELL"  # -15% → short

    assert placed["BBB"]["leverage"] == 75
    assert placed["CCC"]["leverage"] == 100
    assert placed["DDD"]["leverage"] == 20

    leverage_set = {c["symbol"]: c["leverage"] for c in fake.change_leverage_calls}
    assert leverage_set == {"BBB": 75, "CCC": 100, "DDD": 20}

    assert result.details["margin_per_position_usdt"] == "10.00"


@pytest.mark.asyncio
async def test_top_movers_respects_4h_cooldown() -> None:
    """Friss order ugyanarra a stratégiára + szimbólumra → cooldown skip."""
    async with AsyncSessionLocal() as session:
        recent = Order(
            client_order_id="bt-recent-1",
            symbol="BBB",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            quantity=Decimal("0.01"),
            leverage=10,
            status=OrderStatus.NEW,
            strategy_name="top_movers",
        )
        session.add(recent)
        await session.commit()

    fake = FakeBitunixClient(
        tickers=_make_tickers(),
        trading_pairs=_make_pairs(),
        account={"data": {"available": "1000"}},
    )
    strategy = TopMoversStrategy()
    async with AsyncSessionLocal() as session:
        ctx = StrategyContext(
            session=session,
            client=fake,
            settings=get_settings(),
            triggered_by="test",
        )
        result = await strategy.run(ctx)
        await session.commit()

    skipped_symbols = {s["symbol"] for s in result.skipped if s.get("reason") == "cooldown"}
    assert "BBB" in skipped_symbols
    assert all(c["symbol"] != "BBB" for c in fake.change_leverage_calls)


@pytest.mark.asyncio
async def test_top_movers_uses_min_margin_when_balance_low() -> None:
    """5 USDT egyenleg → 1% = 0.05 USDT, de 0.25 minimum lép életbe."""
    fake = FakeBitunixClient(
        tickers={"data": [{"symbol": "ZZZ", "lastPrice": "10", "open": "9"}]},
        trading_pairs={
            "data": [{"symbol": "ZZZ", "maxLeverage": "10", "basePrecision": "2"}]
        },
        account={"data": {"available": "5"}},
    )
    strategy = TopMoversStrategy()
    async with AsyncSessionLocal() as session:
        ctx = StrategyContext(
            session=session,
            client=fake,
            settings=get_settings(),
            triggered_by="test",
        )
        result = await strategy.run(ctx)
        await session.commit()

    assert result.details["margin_per_position_usdt"] == "0.25"


@pytest.mark.asyncio
async def test_top_movers_writes_audit_events() -> None:
    """Minden lényeges lépés DB audit_events-be kerül."""
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(AuditEvent))
        await session.execute(sa.delete(Order))
        await session.commit()

    fake = FakeBitunixClient(
        tickers=_make_tickers(),
        trading_pairs=_make_pairs(),
        account={"data": {"available": "1000"}},
    )
    strategy = TopMoversStrategy()
    async with AsyncSessionLocal() as session:
        ctx = StrategyContext(
            session=session,
            client=fake,
            settings=get_settings(),
            triggered_by="test",
        )
        await strategy.run(ctx)
        await session.commit()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            sa.select(AuditEvent.event, AuditEvent.level).where(
                AuditEvent.strategy_name == "top_movers"
            )
        )
        rows = result.all()

    events = {r.event for r in rows}
    assert "strategy.top_movers.ranked" in events
    assert "strategy.top_movers.margin_computed" in events
    assert "strategy.top_movers.leverage_set" in events
    assert "trade.order_placed" in events
    assert all(r.level == AuditLevel.INFO for r in rows)
