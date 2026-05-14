"""Top signal entries stratégia: belépési logika + integráció fake klienssel."""

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
    CalibrationStatus,
    Order,
    TpSlCalibration,
)
from app.db.session import AsyncSessionLocal, engine
from app.services.calibration import parse_klines
from app.services.strategy.base import StrategyContext
from app.services.strategy.top_movers import _Mover
from app.services.strategy.top_signal_entries import (
    TopSignalEntriesStrategy,
    entry_side_from_mover_and_klines,
)


async def _seed_fresh_calibration() -> None:
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


@pytest.fixture(scope="module", autouse=True)
def _create_schema() -> None:
    asyncio.run(_create_all())


async def _create_all() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _ccc_mover() -> _Mover:
    return _Mover(
        symbol="CCC",
        last_price=Decimal("125"),
        change_pct=Decimal("25"),
        high=Decimal("125"),
        low=Decimal("98"),
    )


def _bbb_mover() -> _Mover:
    return _Mover(
        symbol="BBB",
        last_price=Decimal("60"),
        change_pct=Decimal("-40"),
        high=Decimal("100"),
        low=Decimal("60"),
    )


def _ccc_klines_raw() -> dict:
    return {
        "data": [
            {"time": 1000, "open": "90", "high": "91", "low": "89", "close": "90"},
            {"time": 2000, "open": "99", "high": "100", "low": "98", "close": "99"},
            {"time": 3000, "open": "100", "high": "102", "low": "99.5", "close": "101"},
            {"time": 4000, "open": "101", "high": "101.5", "low": "100", "close": "101.2"},
        ]
    }


def _bbb_klines_raw() -> dict:
    return {
        "data": [
            {"time": 1000, "open": "70", "high": "71", "low": "69", "close": "70"},
            {"time": 2000, "open": "61.5", "high": "61.6", "low": "58", "close": "59"},
            {"time": 3000, "open": "60", "high": "60.1", "low": "57", "close": "56"},
            {"time": 4000, "open": "56", "high": "57", "low": "55", "close": "56.5"},
        ]
    }


def test_entry_side_long_confirm() -> None:
    mover = _ccc_mover()
    kl = parse_klines(_ccc_klines_raw())
    side, reason = entry_side_from_mover_and_klines(
        mover,
        kl,
        min_abs_change_pct=Decimal("1"),
        range_threshold=Decimal("0.6"),
    )
    assert side == "BUY"
    assert reason == "long_breakout_confirm"


def test_entry_side_short_confirm() -> None:
    mover = _bbb_mover()
    kl = parse_klines(_bbb_klines_raw())
    side, reason = entry_side_from_mover_and_klines(
        mover,
        kl,
        min_abs_change_pct=Decimal("1"),
        range_threshold=Decimal("0.6"),
    )
    assert side == "SELL"
    assert reason == "short_breakdown_confirm"


def test_entry_side_rejects_when_range_wrong() -> None:
    """Pozitív változás, de ár nem a felső zónában → nincs long."""
    mover = _Mover(
        symbol="X",
        last_price=Decimal("99"),
        change_pct=Decimal("5"),
        high=Decimal("110"),
        low=Decimal("90"),
    )
    # range pos = (99-90)/(110-90) = 0.45 < 0.6
    kl = parse_klines(_ccc_klines_raw())
    side, reason = entry_side_from_mover_and_klines(
        mover,
        kl,
        min_abs_change_pct=Decimal("1"),
        range_threshold=Decimal("0.6"),
    )
    assert side is None
    assert "mismatch" in reason


def test_entry_side_insufficient_klines() -> None:
    mover = _ccc_mover()
    kl = parse_klines({"data": [{"time": 1, "open": "1", "high": "2", "low": "1", "close": "2"}]})
    side, reason = entry_side_from_mover_and_klines(
        mover,
        kl,
        min_abs_change_pct=Decimal("1"),
        range_threshold=Decimal("0.6"),
    )
    assert side is None
    assert reason == "insufficient_klines"


class _FakeClient:
    def __init__(
        self,
        *,
        tickers: dict,
        trading_pairs: dict,
        account: dict,
        klines_by_symbol: dict[str, dict],
        positions_raw: dict | None = None,
    ) -> None:
        self._tickers = tickers
        self._trading_pairs = trading_pairs
        self._account = account
        self._klines_by_symbol = klines_by_symbol
        self._positions_raw = positions_raw or {"data": []}
        self.place_order_calls: list[dict] = []
        self.get_klines_calls: list[str] = []

    async def get_all_tickers(self) -> dict:
        return self._tickers

    async def get_trading_pairs(self) -> dict:
        return self._trading_pairs

    async def get_account(self, margin_coin: str = "USDT") -> dict:
        return self._account

    async def get_positions(self, symbol: str | None = None) -> dict:
        return self._positions_raw

    async def get_klines(self, symbol: str, **kwargs) -> dict:
        self.get_klines_calls.append(symbol)
        return self._klines_by_symbol.get(symbol, {"data": []})

    async def change_leverage(self, **kwargs) -> dict:
        return {"dryRun": True, "echo": kwargs}

    async def place_order(self, **kwargs) -> dict:
        self.place_order_calls.append(kwargs)
        return {"dryRun": True, "echo": {}}


def _make_tickers() -> dict:
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
async def test_top_signal_entries_disabled_is_no_op() -> None:
    await _seed_fresh_calibration()
    fake = _FakeClient(
        tickers=_make_tickers(),
        trading_pairs=_make_pairs(),
        account={"data": {"available": "1000"}},
        klines_by_symbol={"BBB": _bbb_klines_raw(), "CCC": _ccc_klines_raw()},
    )
    base = get_settings()
    settings = base.model_copy(update={"strategy_top_signal_entries_enabled": False})
    strategy = TopSignalEntriesStrategy()
    async with AsyncSessionLocal() as session:
        ctx = StrategyContext(session=session, client=fake, settings=settings, triggered_by="test")
        result = await strategy.run(ctx)
        await session.commit()
    assert result.details.get("reason") == "disabled"
    assert not fake.place_order_calls


@pytest.mark.asyncio
async def test_top_signal_entries_places_long_and_short_with_signals() -> None:
    await _seed_fresh_calibration()
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(Order))
        await session.commit()

    fake = _FakeClient(
        tickers=_make_tickers(),
        trading_pairs=_make_pairs(),
        account={"data": {"available": "1000"}},
        klines_by_symbol={
            "BBB": _bbb_klines_raw(),
            "CCC": _ccc_klines_raw(),
        },
    )
    base = get_settings()
    settings = base.model_copy(
        update={
            "strategy_top_signal_entries_enabled": True,
            "strategy_top_signal_entries_count": 2,
            "strategy_top_signal_entries_scan_limit": 60,
            "strategy_top_signal_entries_kline_lookahead": 10,
        }
    )
    strategy = TopSignalEntriesStrategy()
    async with AsyncSessionLocal() as session:
        ctx = StrategyContext(session=session, client=fake, settings=settings, triggered_by="test")
        result = await strategy.run(ctx)
        await session.commit()

    placed = {o["symbol"]: o for o in result.placed_orders}
    assert set(placed.keys()) == {"BBB", "CCC"}
    assert placed["BBB"]["side"] == "SELL"
    assert placed["CCC"]["side"] == "BUY"
    assert len(fake.place_order_calls) == 2

    async with AsyncSessionLocal() as session:
        o_rows = (
            await session.execute(
                sa.select(Order).where(Order.strategy_name == "top_signal_entries")
            )
        ).scalars().all()
    assert len(o_rows) == 2
    for o in o_rows:
        assert o.entry_context is not None
        assert o.entry_context.get("strategy") == "top_signal_entries"
        assert "tp_move_pct" in o.entry_context

    async with AsyncSessionLocal() as session:
        rows = (
            (
                await session.execute(
                    sa.select(AuditEvent.event).where(
                        AuditEvent.strategy_name == "top_signal_entries"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert "strategy.top_signal_entries.order_placed" in rows
