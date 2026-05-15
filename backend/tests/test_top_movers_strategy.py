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

from app.bitunix.exceptions import BitunixAPIError
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
        fail_place_order_symbols: frozenset[str] | None = None,
        positions_raw: dict | None = None,
    ) -> None:
        self._tickers = tickers
        self._trading_pairs = trading_pairs
        self._account = account
        self._change_leverage_response = change_leverage_response or {"dryRun": True}
        self._place_order_response = place_order_response or {
            "dryRun": True,
            "echo": {},
        }
        self._fail_place_order_symbols = fail_place_order_symbols or frozenset()
        self._positions_raw = positions_raw or {"data": []}
        self.change_leverage_calls: list[dict] = []
        self.place_order_calls: list[dict] = []

    async def get_all_tickers(self) -> dict:
        return self._tickers

    async def get_trading_pairs(self) -> dict:
        return self._trading_pairs

    async def get_ticker(self, symbol: str) -> dict:
        data = self._tickers.get("data") or []
        if isinstance(data, list):
            for row in data:
                if str(row.get("symbol", "")).upper() == symbol.upper():
                    return {"data": [row]}
        return {"data": [{"symbol": symbol, "lastPrice": "100"}]}

    async def get_account(self, margin_coin: str = "USDT") -> dict:
        return self._account

    async def get_positions(self, symbol: str | None = None) -> dict:
        return self._positions_raw

    async def change_leverage(
        self, *, symbol: str, leverage: int, margin_coin: str = "USDT"
    ) -> dict:
        self.change_leverage_calls.append(
            {"symbol": symbol, "leverage": leverage, "margin_coin": margin_coin}
        )
        return self._change_leverage_response

    async def place_order(self, **kwargs) -> dict:
        self.place_order_calls.append(kwargs)
        sym = str(kwargs.get("symbol", ""))
        if sym in self._fail_place_order_symbols:
            raise BitunixAPIError(
                "The amount should be larger than 700 TRUTH [Bitunix code=30016] | {\"data\": null}",
                code="30016",
                path="/api/v1/futures/trade/place_order",
                response_body={"code": 30016, "data": None, "msg": "The amount should be larger than 700 TRUTH"},
            )
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
async def test_top_movers_uses_global_calibration_without_floor() -> None:
    """Globál medián nyers értéke megy ki (nincs strategy minimum)."""
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
                    "global": {"tp_move_pct": "0.1", "sl_move_pct": "0.08"},
                    "per_symbol": {},
                },
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            )
        )
        await session.commit()

    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(Order))
        await session.commit()

    tickers = {
        "data": [
            {
                "symbol": "FFF",
                "lastPrice": "60",
                "open": "100",
                "high": "100",
                "low": "60",
            },
        ]
    }
    pairs = {
        "data": [
            {
                "symbol": "FFF",
                "maxLeverage": "10",
                "basePrecision": "2",
                "pricePrecision": "2",
            },
        ]
    }
    fake = FakeBitunixClient(
        tickers=tickers,
        trading_pairs=pairs,
        account={"data": {"available": "1000"}},
    )
    base = get_settings()
    settings = base.model_copy(
        update={
            "strategy_top_movers_count": 1,
            "strategy_top_movers_scan_limit": 5,
        }
    )
    strategy = TopMoversStrategy()
    async with AsyncSessionLocal() as session:
        ctx = StrategyContext(
            session=session, client=fake, settings=settings, triggered_by="test"
        )
        result = await strategy.run(ctx)
        await session.commit()

    assert len(result.placed_orders) == 1
    placed = result.placed_orders[0]
    assert placed["symbol"] == "FFF"
    assert placed["tp_source"] == "calibration_global"
    assert Decimal(placed["tp_move_pct"]) == Decimal("0.1")
    assert Decimal(placed["sl_move_pct"]) == Decimal("0.08")
    assert Decimal(placed["tp_price"]) == Decimal("59.94")
    assert Decimal(placed["sl_price"]) == Decimal("60.05")


@pytest.mark.asyncio
async def test_top_movers_skips_symbol_when_place_order_rejected() -> None:
    """Bitunix elutasítás (pl. min. mennyiség) egy coinon → a többi tovább megy."""
    await _seed_fresh_calibration()
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(Order))
        await session.commit()
    fake = FakeBitunixClient(
        tickers=_make_tickers(),
        trading_pairs=_make_pairs(),
        account={"data": {"available": "1000"}},
        fail_place_order_symbols=frozenset({"BBB"}),
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

    assert len(result.placed_orders) == 3
    assert {o["symbol"] for o in result.placed_orders} == {"AAA", "CCC", "DDD"}
    bbb_skip = next(s for s in result.skipped if s.get("symbol") == "BBB")
    assert bbb_skip.get("reason") == "place_order_rejected"
    assert bbb_skip.get("bitunix_code") == "30016"

    async with AsyncSessionLocal() as session:
        orders = (await session.scalars(sa.select(Order))).all()
    assert len(orders) == 3

    async with AsyncSessionLocal() as session:
        n_failed = await session.scalar(
            sa.select(sa.func.count(AuditEvent.id)).where(
                AuditEvent.event == "strategy.top_movers.place_order_failed"
            )
        )
    assert n_failed == 1


@pytest.mark.asyncio
async def test_top_movers_fills_only_missing_slots_when_one_position_open() -> None:
    """1 nyitott pozíció (BBB) → még 2 új belépés a rangsor szerint."""
    await _seed_fresh_calibration()
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(Order))
        await session.commit()
    fake = FakeBitunixClient(
        tickers=_make_tickers(),
        trading_pairs=_make_pairs(),
        account={"data": {"available": "1000"}},
        positions_raw={"data": [{"symbol": "BBB", "positionAmt": "1"}]},
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

    assert len(result.placed_orders) == 2
    assert {o["symbol"] for o in result.placed_orders} == {"CCC", "DDD"}
    assert any(
        s.get("symbol") == "BBB" and s.get("reason") == "position_already_open"
        for s in result.skipped
    )


@pytest.mark.asyncio
async def test_top_movers_no_new_orders_when_slot_cap_reached() -> None:
    """3 nyitott pozíció → slots_full, nincs új place_order."""
    await _seed_fresh_calibration()
    fake = FakeBitunixClient(
        tickers=_make_tickers(),
        trading_pairs=_make_pairs(),
        account={"data": {"available": "1000"}},
        positions_raw={
            "data": [
                {"symbol": "BBB", "positionAmt": "1"},
                {"symbol": "CCC", "positionAmt": "1"},
                {"symbol": "DDD", "positionAmt": "1"},
            ]
        },
    )
    strategy = TopMoversStrategy()
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(Order))
        await session.commit()
        ctx = StrategyContext(
            session=session,
            client=fake,
            settings=get_settings(),
            triggered_by="test",
        )
        result = await strategy.run(ctx)
        await session.commit()

    assert result.placed_orders == []
    assert fake.place_order_calls == []

    async with AsyncSessionLocal() as session:
        ev = await session.scalar(
            sa.select(AuditEvent.event).where(
                AuditEvent.event == "strategy.top_movers.slots_full"
            )
        )
    assert ev == "strategy.top_movers.slots_full"


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
    assert "strategy.top_movers.tpsl_set" in events
    assert "trade.order_placed" in events
    levels = {r.event: r.level for r in rows}
    assert levels["strategy.top_movers.tpsl_set"] == AuditLevel.INFO


@pytest.mark.asyncio
async def test_top_movers_skips_when_tp_margin_roi_below_config_min() -> None:
    """Ha a számolt TP margin-ROI (tp_move × lev) < strategy_min_tp_roi_pct, skip."""
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
                    "global": {"tp_move_pct": "0.5", "sl_move_pct": "0.25"},
                    "per_symbol": {},
                },
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            )
        )
        await session.execute(sa.delete(Order))
        await session.commit()

    fake = FakeBitunixClient(
        tickers={
            "data": [
                {
                    "symbol": "ZZZ",
                    "lastPrice": "110",
                    "open": "100",
                    "high": "110",
                    "low": "100",
                }
            ]
        },
        trading_pairs={
            "data": [
                {
                    "symbol": "ZZZ",
                    "maxLeverage": "20",
                    "basePrecision": "2",
                    "pricePrecision": "2",
                }
            ]
        },
        account={"data": {"available": "1000"}},
    )
    base = get_settings()
    settings = base.model_copy(
        update={
            "strategy_top_movers_count": 1,
            "strategy_top_movers_scan_limit": 5,
            "strategy_top_movers_direction_mode": "trend",
            "strategy_min_tp_roi_pct": "60",
        }
    )
    strategy = TopMoversStrategy()
    async with AsyncSessionLocal() as session:
        ctx = StrategyContext(
            session=session, client=fake, settings=settings, triggered_by="test"
        )
        result = await strategy.run(ctx)
        await session.commit()

    assert result.placed_orders == []
    assert any(s.get("reason") == "tp_roi_below_min" for s in result.skipped)
    assert fake.place_order_calls == []
