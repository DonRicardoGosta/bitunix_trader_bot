"""Integrációs teszt: ``TradingService.list_orders`` pozíció-szintű enrichment.

A teszt egy minimal in-memory ``FakeBitunixClient``-tel hívja a service-t és
ellenőrzi, hogy a Bitunix history-positions / pending-positions adatait helyesen
köti az adatbázisban tárolt rendelésekhez.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

# A list_orders alap lookback 6 óra; a seedelt tesztadatok régebbiek lehetnek.
_TEST_LOOKBACK_H = 2160
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa

from app.db.base import Base
from app.db.models import Order, OrderSide, OrderStatus, OrderType
from app.db.session import AsyncSessionLocal, engine
from app.services.trading import (
    TradingService,
    _enrichment_cache,
    clear_orders_enrichment_cache,
)


@pytest.fixture(scope="module", autouse=True)
def _create_schema() -> None:
    asyncio.run(_create_all())


async def _create_all() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


class _FakeClient:
    """A list_orders által hívott Bitunix metódusok minimal mockja."""

    def __init__(
        self,
        *,
        positions: list[dict[str, Any]] | None = None,
        history_positions: dict[str, list[dict[str, Any]]] | None = None,
        history_orders: dict[str, list[dict[str, Any]]] | None = None,
        history_trades: dict[str, list[dict[str, Any]]] | None = None,
        tickers: dict[str, str] | None = None,
    ) -> None:
        self._positions = positions or []
        self._history_positions = history_positions or {}
        self._history_orders = history_orders or {}
        self._history_trades = history_trades or {}
        self._tickers = tickers or {}
        self.bitunix_call_count = 0

    def _bump(self) -> None:
        self.bitunix_call_count += 1

    async def get_positions(self, symbol: str | None = None) -> dict[str, Any]:
        self._bump()
        return {"code": 0, "data": list(self._positions)}

    async def get_history_positions(
        self, *, symbol: str | None = None, **_: Any
    ) -> dict[str, Any]:
        self._bump()
        rows = self._history_positions.get(symbol or "", [])
        return {"code": 0, "data": {"total": str(len(rows)), "positionList": list(rows)}}

    async def get_history_orders(
        self, *, symbol: str | None = None, **_: Any
    ) -> dict[str, Any]:
        self._bump()
        rows = self._history_orders.get(symbol or "", [])
        return {"code": 0, "data": {"total": str(len(rows)), "orderList": list(rows)}}

    async def get_history_trades(
        self, *, symbol: str | None = None, **_: Any
    ) -> dict[str, Any]:
        self._bump()
        rows = self._history_trades.get(symbol or "", [])
        return {"code": 0, "data": {"total": str(len(rows)), "tradeList": list(rows)}}

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        self._bump()
        price = self._tickers.get(symbol)
        return (
            {"code": 0, "data": [{"symbol": symbol, "lastPrice": price, "markPrice": price}]}
            if price is not None
            else {"code": 0, "data": []}
        )


async def _seed_orders(rows: list[dict[str, Any]]) -> None:
    """Tesztrekordok beszúrása az ``orders`` táblába megadott ``created_at``-tel."""
    clear_orders_enrichment_cache()
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(Order))
        for row in rows:
            o = Order(
                client_order_id=row["client_order_id"],
                bitunix_order_id=row.get("bitunix_order_id"),
                symbol=row["symbol"],
                side=row["side"],
                type=row.get("type", OrderType.MARKET),
                quantity=row["quantity"],
                price=row.get("price"),
                leverage=row["leverage"],
                status=row.get("status", OrderStatus.NEW),
                reduce_only=row.get("reduce_only", False),
                entry_context=row.get("entry_context"),
            )
            session.add(o)
            await session.flush()
            o.created_at = row["created_at"]
            o.updated_at = row["created_at"]
        await session.commit()


@pytest.mark.asyncio
async def test_list_orders_uses_open_position_realized_and_unrealized() -> None:
    """Egy nyitott pozícióhoz tartozó belépő rendelés mutassa az unrealizedet."""
    when = datetime.fromtimestamp(1778681838.0, tz=UTC)
    await _seed_orders([
        {
            "client_order_id": "bt-open-1",
            "symbol": "MLNUSDT",
            "side": OrderSide.SELL,
            "quantity": Decimal("5.81"),
            "price": None,
            "leverage": 50,
            "status": OrderStatus.NEW,
            "created_at": when,
        }
    ])
    fake = _FakeClient(
        positions=[
            {
                "positionId": "p-open-1",
                "symbol": "MLNUSDT",
                "side": "SELL",
                "qty": "5.81",
                "leverage": 50,
                "ctime": "1778681838000",
                "realizedPNL": "-0.007679658",
                "unrealizedPNL": "0.05229",
                "margin": "0.263668258",
                "avgOpenPrice": "2.203",
            }
        ],
    )
    async with AsyncSessionLocal() as session:
        svc = TradingService(client=fake, session=session)  # type: ignore[arg-type]
        rows = await svc.list_orders(lookback_hours=_TEST_LOOKBACK_H)
    assert len(rows) == 1
    ex = rows[0]["exchange"]
    assert ex["lifecycle"] == "open"
    assert ex["realized_pnl_usdt"] == "-0.007679658"
    assert ex["unrealized_pnl_usdt"] == "0.05229"
    assert ex["position_id"] == "p-open-1"
    # (-0.007679658 + 0.05229) / 0.263668258 * 100 ≈ 16.92
    assert ex["roi_pct"] == "16.92"


@pytest.mark.asyncio
async def test_list_orders_matches_by_history_order_position_id() -> None:
    """Ha a history order tartalmaz positionId-t, az elsődleges párosítás."""
    when = datetime.fromtimestamp(1778681838.0, tz=UTC)
    await _seed_orders([
        {
            "client_order_id": "bt-by-pid",
            "bitunix_order_id": "ord-pid",
            "symbol": "SAGAUSDT",
            "side": OrderSide.SELL,
            "quantity": Decimal("100"),
            "price": None,
            "leverage": 10,
            "status": OrderStatus.NEW,
            "created_at": when,
        }
    ])
    fake = _FakeClient(
        history_orders={
            "SAGAUSDT": [
                {
                    "orderId": "ord-pid",
                    "clientId": "bt-by-pid",
                    "symbol": "SAGAUSDT",
                    "positionId": "p-from-hist",
                    "qty": "100",
                    "status": "FILLED",
                    "realizedPNL": "0",
                    "mtime": int(when.timestamp() * 1000),
                }
            ]
        },
        history_positions={
            "SAGAUSDT": [
                {
                    "positionId": "p-from-hist",
                    "symbol": "SAGAUSDT",
                    "side": "SELL",
                    "maxQty": "100",
                    "ctime": "1778681500000",
                    "realizedPNL": "7.25",
                    "entryPrice": "1",
                    "closePrice": "1.1",
                    "leverage": "10",
                }
            ]
        },
    )
    async with AsyncSessionLocal() as session:
        svc = TradingService(client=fake, session=session)  # type: ignore[arg-type]
        rows = await svc.list_orders(lookback_hours=_TEST_LOOKBACK_H)
    ex = rows[0]["exchange"]
    assert ex["realized_pnl_usdt"] == "7.25"
    assert ex["lifecycle"] == "closed"
    assert ex["position_id"] == "p-from-hist"


@pytest.mark.asyncio
async def test_list_orders_uses_history_position_realized_for_closed() -> None:
    when = datetime.fromtimestamp(1778681838.0, tz=UTC)
    await _seed_orders([
        {
            "client_order_id": "bt-closed-1",
            "symbol": "SAGAUSDT",
            "side": OrderSide.SELL,
            "quantity": Decimal("468.6"),
            "price": None,
            "leverage": 50,
            "status": OrderStatus.NEW,
            "created_at": when,
        }
    ])
    fake = _FakeClient(
        history_positions={
            "SAGAUSDT": [
                {
                    "positionId": "p-closed-1",
                    "symbol": "SAGAUSDT",
                    "side": "SELL",
                    "maxQty": "468.6",
                    "leverage": "50",
                    "ctime": "1778681838000",
                    "mtime": "1778681865000",
                    "entryPrice": "0.02811",
                    "closePrice": "0.02804",
                    "realizedPNL": "0.017014866",
                }
            ]
        },
    )
    async with AsyncSessionLocal() as session:
        svc = TradingService(client=fake, session=session)  # type: ignore[arg-type]
        rows = await svc.list_orders(lookback_hours=_TEST_LOOKBACK_H)
    ex = rows[0]["exchange"]
    assert ex["lifecycle"] == "closed"
    assert ex["realized_pnl_usdt"] == "0.017014866"
    assert ex["unrealized_pnl_usdt"] is None
    assert ex["position_id"] == "p-closed-1"


@pytest.mark.asyncio
async def test_list_orders_no_position_match_falls_back_to_hist_orders() -> None:
    """Ha sem nyitott, sem lezárt pozíció nem párosítható, használjuk a hist_orders-t."""
    when = datetime.fromtimestamp(1778600000.0, tz=UTC)
    await _seed_orders([
        {
            "client_order_id": "bt-fallback-1",
            "bitunix_order_id": "ord-1",
            "symbol": "BTCUSDT",
            "side": OrderSide.BUY,
            "quantity": Decimal("1"),
            "price": Decimal("60000"),
            "leverage": 10,
            "status": OrderStatus.NEW,
            "created_at": when,
            "reduce_only": True,
        }
    ])
    fake = _FakeClient(
        history_orders={
            "BTCUSDT": [
                {
                    "orderId": "ord-1",
                    "clientId": "bt-fallback-1",
                    "symbol": "BTCUSDT",
                    "qty": "1",
                    "tradeQty": "1",
                    "avgPrice": "60000",
                    "price": "60000",
                    "leverage": 10,
                    "status": "FILLED",
                    "realizedPNL": "100",
                    "mtime": int(when.timestamp() * 1000),
                }
            ]
        },
    )
    async with AsyncSessionLocal() as session:
        svc = TradingService(client=fake, session=session)  # type: ignore[arg-type]
        rows = await svc.list_orders(lookback_hours=_TEST_LOOKBACK_H)
    ex = rows[0]["exchange"]
    assert ex["realized_pnl_usdt"] == "100"
    # margin = 1*60000/10 = 6000 → ROI = 100/6000*100 = 1.6667 → "1.67"
    assert ex["roi_pct"] == "1.67"
    assert ex["position_id"] is None


@pytest.mark.asyncio
async def test_list_orders_handles_position_history_api_error() -> None:
    """Ha a get_history_positions hibázik, ne robbanjon a service – csak sync_error."""
    when = datetime.now(UTC) - timedelta(minutes=5)
    await _seed_orders([
        {
            "client_order_id": "bt-err-1",
            "symbol": "BTCUSDT",
            "side": OrderSide.BUY,
            "quantity": Decimal("1"),
            "price": None,
            "leverage": 10,
            "status": OrderStatus.NEW,
            "created_at": when,
        }
    ])

    from app.bitunix.exceptions import BitunixAPIError

    class _ErrClient(_FakeClient):
        async def get_history_positions(self, **kwargs: Any) -> dict[str, Any]:
            raise BitunixAPIError("upstream 500", path="/api/v1/futures/position/get_history_positions")

    fake = _ErrClient()
    async with AsyncSessionLocal() as session:
        svc = TradingService(client=fake, session=session)  # type: ignore[arg-type]
        rows = await svc.list_orders(lookback_hours=_TEST_LOOKBACK_H)
    # Hiba esetén nem dőlünk el; a sync_error mező mutatja a problémát.
    assert len(rows) == 1
    assert rows[0]["exchange"]["sync_error"] is None or "history" in rows[0]["exchange"]["sync_error"].lower()


@pytest.mark.asyncio
async def test_orders_pnl_totals_matches_sum_of_list_orders_rows() -> None:
    """``orders_pnl_totals`` ugyanazt az enrichmentet futtatja, mint a lista (összes DB sor)."""
    when = datetime.fromtimestamp(1778681838.0, tz=UTC)
    await _seed_orders(
        [
            {
                "client_order_id": "bt-pnl-open",
                "symbol": "MLNUSDT",
                "side": OrderSide.SELL,
                "quantity": Decimal("5.81"),
                "price": None,
                "leverage": 50,
                "status": OrderStatus.NEW,
                "created_at": when,
            },
            {
                "client_order_id": "bt-pnl-closed",
                "symbol": "SAGAUSDT",
                "side": OrderSide.SELL,
                "quantity": Decimal("468.6"),
                "price": None,
                "leverage": 50,
                "status": OrderStatus.NEW,
                "created_at": when,
            },
        ],
    )
    fake = _FakeClient(
        positions=[
            {
                "positionId": "p-open-pnl",
                "symbol": "MLNUSDT",
                "side": "SELL",
                "qty": "5.81",
                "leverage": 50,
                "ctime": "1778681838000",
                "realizedPNL": "-0.007679658",
                "unrealizedPNL": "0.05229",
                "margin": "0.263668258",
                "avgOpenPrice": "2.203",
            }
        ],
        history_positions={
            "SAGAUSDT": [
                {
                    "positionId": "p-closed-pnl",
                    "symbol": "SAGAUSDT",
                    "side": "SELL",
                    "maxQty": "468.6",
                    "leverage": "50",
                    "ctime": "1778681838000",
                    "mtime": "1778681865000",
                    "entryPrice": "0.02811",
                    "closePrice": "0.02804",
                    "realizedPNL": "0.017014866",
                }
            ]
        },
    )
    async with AsyncSessionLocal() as session:
        svc = TradingService(client=fake, session=session)  # type: ignore[arg-type]
        totals = await svc.orders_pnl_totals(lookback_hours=_TEST_LOOKBACK_H)
        rows = await svc.list_orders(limit=100, lookback_hours=_TEST_LOOKBACK_H)
    assert len(rows) == 2
    sum_r = sum(
        Decimal(str(r["exchange"].get("realized_pnl_usdt") or "0")) for r in rows
    )
    sum_u = sum(
        Decimal(str(r["exchange"].get("unrealized_pnl_usdt") or "0")) for r in rows
    )
    assert totals["order_count"] == 2
    assert Decimal(totals["realized_pnl_usdt"]) == sum_r
    assert Decimal(totals["unrealized_pnl_usdt"]) == sum_u
    assert Decimal(totals["total_pnl_usdt"]) == sum_r + sum_u


@pytest.mark.asyncio
async def test_list_orders_and_pnl_totals_share_enrichment_cache() -> None:
    """Párhuzamos UI hívások ne duplázzák a Bitunix szinkront."""
    when = datetime.fromtimestamp(1778681838.0, tz=UTC)
    await _seed_orders([
        {
            "client_order_id": "bt-cache-1",
            "symbol": "MLNUSDT",
            "side": OrderSide.SELL,
            "quantity": Decimal("1"),
            "price": None,
            "leverage": 10,
            "status": OrderStatus.NEW,
            "created_at": when,
        }
    ])
    fake = _FakeClient(
        positions=[
            {
                "positionId": "p-cache",
                "symbol": "MLNUSDT",
                "side": "SELL",
                "qty": "1",
                "leverage": 10,
                "ctime": "1778681838000",
                "realizedPNL": "0",
                "unrealizedPNL": "0.1",
                "margin": "1",
                "avgOpenPrice": "1",
            }
        ],
    )
    _enrichment_cache.clear()
    async with AsyncSessionLocal() as session:
        svc = TradingService(client=fake, session=session)  # type: ignore[arg-type]
        await svc.list_orders(lookback_hours=_TEST_LOOKBACK_H)
        calls_after_list = fake.bitunix_call_count
        await svc.orders_pnl_totals(lookback_hours=_TEST_LOOKBACK_H)
    assert fake.bitunix_call_count == calls_after_list


@pytest.mark.asyncio
async def test_list_orders_includes_entry_context_from_db() -> None:
    when = datetime.fromtimestamp(1778681838.0, tz=UTC)
    ctx = {
        "strategy": "top_signal_entries",
        "tp_source": "walk_forward_recommendation",
    }
    await _seed_orders([
        {
            "client_order_id": "bt-ctx-1",
            "symbol": "XRPUSDT",
            "side": OrderSide.BUY,
            "quantity": Decimal("1"),
            "price": None,
            "leverage": 10,
            "status": OrderStatus.NEW,
            "created_at": when,
            "entry_context": ctx,
        }
    ])
    fake = _FakeClient()
    async with AsyncSessionLocal() as session:
        svc = TradingService(client=fake, session=session)  # type: ignore[arg-type]
        rows = await svc.list_orders(limit=10, lookback_hours=_TEST_LOOKBACK_H)
    assert len(rows) == 1
    assert rows[0]["entry_context"] == ctx
