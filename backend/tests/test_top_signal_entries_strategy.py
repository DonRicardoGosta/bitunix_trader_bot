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
    AppRuntimeSetting,
    AuditEvent,
    CalibrationStatus,
    Order,
    TpSlCalibration,
)
from app.db.session import AsyncSessionLocal, engine
from app.services.calibration import parse_klines
from app.services.strategy.base import StrategyContext
from app.services.strategy.mover_ranking import Mover
from app.services.runtime_settings import set_runtime_bool
from app.services.strategy.top_signal_entries import (
    TopSignalEntriesStrategy,
    entry_side_from_mover_and_klines,
)
from tests.strategy_test_context import make_strategy_context


@pytest.fixture(autouse=True)
def _allow_entry_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.strategy.top_signal_entries.is_hour_quarter_entry_now",
        lambda *_a, **_k: True,
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


@pytest.fixture(autouse=True)
async def _clear_strategy_runtime_override() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            sa.delete(AppRuntimeSetting).where(
                AppRuntimeSetting.key == "strategy_top_signal_entries_enabled"
            )
        )
        await session.commit()


async def _create_all() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _ccc_mover() -> Mover:
    return Mover(
        symbol="CCC",
        last_price=Decimal("125"),
        change_pct=Decimal("25"),
        high=Decimal("125"),
        low=Decimal("98"),
    )


def _bbb_mover() -> Mover:
    return Mover(
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
    mover = Mover(
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
        self.change_leverage_calls: list[dict] = []
        self.place_position_tp_sl_calls: list[dict] = []
        self._open_positions: dict[tuple[str, str], str] = {}
        self.get_klines_calls: list[str] = []

    async def get_all_tickers(self) -> dict:
        return self._tickers

    async def get_trading_pairs(self) -> dict:
        return self._trading_pairs

    async def get_account(self, margin_coin: str = "USDT") -> dict:
        return self._account

    async def get_positions(self, symbol: str | None = None) -> dict:
        rows = []
        for (sym, side), pid in self._open_positions.items():
            if symbol and sym != symbol.upper():
                continue
            rows.append(
                {
                    "symbol": sym,
                    "side": side,
                    "positionId": pid,
                    "qty": "1",
                }
            )
        if rows:
            return {"data": rows}
        return self._positions_raw

    async def get_ticker(self, symbol: str) -> dict:
        data = self._tickers.get("data") or []
        if isinstance(data, list):
            for row in data:
                if str(row.get("symbol", "")).upper() == symbol.upper():
                    return {"data": [row]}
        return {"data": [{"symbol": symbol, "lastPrice": "100"}]}

    async def get_klines(self, symbol: str, **kwargs) -> dict:
        self.get_klines_calls.append(symbol)
        return self._klines_by_symbol.get(symbol, {"data": []})

    async def change_leverage(self, **kwargs) -> dict:
        self.change_leverage_calls.append(kwargs)
        return {"dryRun": True, "echo": kwargs}

    async def place_order(self, **kwargs) -> dict:
        self.place_order_calls.append(kwargs)
        sym = str(kwargs.get("symbol", "")).upper()
        side = str(kwargs.get("side", "BUY")).upper()
        if kwargs.get("trade_side", "OPEN") == "OPEN" and not kwargs.get("reduce_only"):
            self._open_positions[(sym, side)] = f"pos-{sym}"
        return {"dryRun": True, "echo": {}}

    async def place_position_tp_sl_order(self, **kwargs) -> dict:
        self.place_position_tp_sl_calls.append(kwargs)
        return {"dryRun": True, "data": {"orderId": "tpsl-mock"}, "echo": kwargs}


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
    strategy = TopSignalEntriesStrategy()
    async with AsyncSessionLocal() as session:
        await set_runtime_bool(session, "strategy_top_signal_entries_enabled", False)
        await session.commit()
    async with AsyncSessionLocal() as session:
        ctx = make_strategy_context(session, fake, triggered_by="test")
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
    strategy = TopSignalEntriesStrategy()
    async with AsyncSessionLocal() as session:
        await set_runtime_bool(session, "strategy_top_signal_entries_enabled", True)
        await session.commit()
    async with AsyncSessionLocal() as session:
        ctx = make_strategy_context(
            session,
            fake,
            triggered_by="test",
            count=2,
            scan_limit=60,
            kline_lookahead=10,
            wf_gate_enabled=False,
            min_tp_roi_pct="0",
        )
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


def _highlev_klines_raw() -> dict:
    return _ccc_klines_raw()


@pytest.mark.asyncio
async def test_top_signal_entries_caps_leverage_for_order_request() -> None:
    """maxLeverage=200 a tőzsdén → belső rendelés legfeljebb 125 (OrderRequest)."""
    await _seed_fresh_calibration()
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(Order))
        await session.commit()

    tickers = {
        "data": [
            {
                "symbol": "HIGHLEV",
                "lastPrice": "150",
                "open": "100",
                "high": "150",
                "low": "98",
            },
        ]
    }
    pairs = {
        "data": [
            {
                "symbol": "HIGHLEV",
                "maxLeverage": "200",
                "basePrecision": "4",
                "pricePrecision": "2",
            },
        ]
    }
    fake = _FakeClient(
        tickers=tickers,
        trading_pairs=pairs,
        account={"data": {"available": "1000"}},
        klines_by_symbol={"HIGHLEV": _highlev_klines_raw()},
    )
    strategy = TopSignalEntriesStrategy()
    async with AsyncSessionLocal() as session:
        await set_runtime_bool(session, "strategy_top_signal_entries_enabled", True)
        await session.commit()
    async with AsyncSessionLocal() as session:
        ctx = make_strategy_context(
            session,
            fake,
            triggered_by="test",
            count=1,
            scan_limit=10,
            kline_lookahead=10,
            wf_gate_enabled=False,
            min_tp_roi_pct="0",
        )
        result = await strategy.run(ctx)
        await session.commit()

    assert len(result.placed_orders) == 1
    placed = result.placed_orders[0]
    assert placed["symbol"] == "HIGHLEV"
    assert placed["leverage"] == 125
    assert placed.get("leverage_capped") is True
    assert placed.get("pair_max_leverage") == 200
    assert len(fake.place_order_calls) == 1
    assert len(fake.change_leverage_calls) == 1
    assert fake.change_leverage_calls[0]["leverage"] == 125
    assert fake.change_leverage_calls[0]["symbol"] == "HIGHLEV"

    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                sa.select(Order).where(Order.symbol == "HIGHLEV")
            )
        ).scalar_one()
    assert row.leverage == 125
