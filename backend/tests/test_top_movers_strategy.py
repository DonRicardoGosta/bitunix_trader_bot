"""Top movers stratégia end-to-end integráció (in-memory sqlite + fake kliens).

A Bitunix klienst egy ``FakeBitunixClient`` helyettesíti, amely előre megadott
válaszokat ad. Így a teljes ``TopMoversStrategy.run`` lefuttatható DB-vel,
és tudjuk ellenőrizni az audit eseményeket, a cooldownt és a kerekítést.

Minden teszt egy friss SUCCESS ``TpSlCalibration`` rekorddal indul, hogy a
kalibrációs gate ne akadályozza a kereskedést – a gate viselkedését külön
``test_calibration_gating.py`` ellenőrzi.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.config import get_settings
from app.db.base import Base
from app.db.models import (
    AuditEvent,
    AuditLevel,
    CalibrationStatus,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    TpSlCalibration,
)
from app.db.session import AsyncSessionLocal, engine
from app.services.strategy.base import StrategyContext
from app.services.strategy.top_movers import TopMoversStrategy


async def _seed_fresh_calibration() -> None:
    """Friss SUCCESS kalibráció DB-be – per-symbol nélkül (global fallback)."""
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(TpSlCalibration))
        session.add(
            TpSlCalibration(
                status=CalibrationStatus.SUCCESS,
                triggered_by="test_setup",
                lookback_minutes=120,
                top_n=20,
                summary={
                    "lookback_minutes": 120,
                    "top_n": 20,
                    "tp_atr_mult": "3.0",
                    "sl_atr_mult": "1.5",
                    "global": {"tp_move_pct": "1.5", "sl_move_pct": "0.75"},
                    "per_symbol": {},
                },
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            )
        )
        await session.commit()


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
    """Olyan tickerek, ahol a top3 mover egyértelmű breakout-ban van.

    AAA  +10% (kihagyva, top3-on kívül)
    BBB  -40% (top), last=60, high=100, low=60   → pos=0/40=0.0 → SELL
    CCC  +25%       last=125, high=125, low=98   → pos=27/27=1.0 → BUY
    DDD  -15%       last=85, high=100, low=85    → pos=0/15=0.0 → SELL
    EEE  +1%
    """
    return {
        "data": [
            {"symbol": "AAA", "lastPrice": "110", "open": "100", "high": "115", "low": "98"},
            {"symbol": "BBB", "lastPrice": "60", "open": "100", "high": "100", "low": "60"},
            {"symbol": "CCC", "lastPrice": "125", "open": "100", "high": "125", "low": "98"},
            {"symbol": "DDD", "lastPrice": "85", "open": "100", "high": "100", "low": "85"},
            {"symbol": "EEE", "lastPrice": "101", "open": "100", "high": "102", "low": "100"},
        ]
    }


def _make_pairs() -> dict:
    return {
        "data": [
            {"symbol": "AAA", "maxLeverage": "50", "basePrecision": "3", "pricePrecision": "2"},
            {"symbol": "BBB", "maxLeverage": "75", "basePrecision": "2", "pricePrecision": "2"},
            {"symbol": "CCC", "maxLeverage": "100", "basePrecision": "4", "pricePrecision": "2"},
            {"symbol": "DDD", "maxLeverage": "20", "basePrecision": "1", "pricePrecision": "2"},
        ]
    }


@pytest.mark.asyncio
async def test_top_movers_places_orders_for_top3_with_correct_direction() -> None:
    """Top3 absolute mover → három rendelés, irány a breakout helyzettel összhangban,
    TP/SL trigger árak natívan az entry order paraméterei között.
    """
    await _seed_fresh_calibration()
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(Order))
        await session.commit()
    fake = FakeBitunixClient(
        tickers=_make_tickers(),
        trading_pairs=_make_pairs(),
        account={"data": {"available": "1000"}},  # 1% → 10 USDT margin
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
    assert placed["BBB"]["side"] == "SELL"
    assert placed["CCC"]["side"] == "BUY"
    assert placed["DDD"]["side"] == "SELL"

    assert placed["BBB"]["leverage"] == 75
    assert placed["CCC"]["leverage"] == 100
    assert placed["DDD"]["leverage"] == 20

    leverage_set = {c["symbol"]: c["leverage"] for c in fake.change_leverage_calls}
    assert leverage_set == {"BBB": 75, "CCC": 100, "DDD": 20}

    # TP/SL az entry order-en megy a Bitunixhoz
    by_symbol = {c["symbol"]: c for c in fake.place_order_calls}
    for sym in ("BBB", "CCC", "DDD"):
        assert by_symbol[sym]["tp_price"] is not None
        assert by_symbol[sym]["sl_price"] is not None
        assert by_symbol[sym]["tp_stop_type"] == "MARK_PRICE"
        assert by_symbol[sym]["sl_stop_type"] == "MARK_PRICE"
        assert by_symbol[sym]["trade_side"] == "OPEN"

    # Kalibráció globális fallback: tp_move=1.5%, sl_move=0.75%
    # +25% CCC LONG  entry=125 → tp=126.87(5), sl=124.06(25), 2 dec round_down
    assert Decimal(placed["CCC"]["tp_price"]) == Decimal("126.87")
    assert Decimal(placed["CCC"]["sl_price"]) == Decimal("124.06")
    # -40% BBB SHORT entry=60 → tp=59.10, sl=60.45 (round_up 2dec)
    assert Decimal(placed["BBB"]["tp_price"]) == Decimal("59.10")
    assert Decimal(placed["BBB"]["sl_price"]) == Decimal("60.45")
    assert placed["BBB"]["tp_source"] == "calibration_global"

    assert result.details["margin_per_position_usdt"] == "10.00"
    assert result.details["calibration_used"] is True


@pytest.mark.asyncio
async def test_top_movers_respects_4h_cooldown() -> None:
    """Friss order ugyanarra a stratégiára + szimbólumra → cooldown skip."""
    await _seed_fresh_calibration()
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(Order))
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
    await _seed_fresh_calibration()
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(Order))
        await session.commit()
    fake = FakeBitunixClient(
        tickers={
            "data": [
                {"symbol": "ZZZ", "lastPrice": "10", "open": "9", "high": "10", "low": "9"}
            ]
        },
        trading_pairs={
            "data": [
                {
                    "symbol": "ZZZ",
                    "maxLeverage": "10",
                    "basePrecision": "2",
                    "pricePrecision": "2",
                }
            ]
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
async def test_top_movers_skips_ambiguous_in_momentum_breakout_mode() -> None:
    """Ha az ár a 24h tartomány közepén van, ne nyissunk pozíciót."""
    await _seed_fresh_calibration()
    fake = FakeBitunixClient(
        tickers={
            "data": [
                # +30% mover de range közepén (last=100, high=110, low=90 → pos=0.5)
                {
                    "symbol": "MID",
                    "lastPrice": "100",
                    "open": "77",
                    "high": "110",
                    "low": "90",
                },
            ]
        },
        trading_pairs={
            "data": [
                {
                    "symbol": "MID",
                    "maxLeverage": "20",
                    "basePrecision": "2",
                    "pricePrecision": "2",
                }
            ]
        },
        account={"data": {"available": "1000"}},
    )
    strategy = TopMoversStrategy()
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(Order))
        await session.commit()
        ctx = StrategyContext(
            session=session, client=fake, settings=get_settings(), triggered_by="test"
        )
        result = await strategy.run(ctx)
        await session.commit()

    assert result.placed_orders == []
    assert len(result.skipped) == 1
    assert result.skipped[0]["reason"] == "direction_skip"
    assert "mixed" in result.skipped[0]["direction_reason"]
    # leverage sem lett beállítva (mert a skip előbb történt)
    assert fake.change_leverage_calls == []


@pytest.mark.asyncio
async def test_top_movers_writes_audit_events() -> None:
    """Minden lényeges lépés DB audit_events-be kerül."""
    await _seed_fresh_calibration()
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
    assert "strategy.top_movers.tpsl_set" in events
    assert "trade.order_placed" in events
    levels = {r.event: r.level for r in rows}
    assert levels["strategy.top_movers.tpsl_set"] == AuditLevel.INFO
