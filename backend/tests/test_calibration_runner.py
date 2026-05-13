"""CalibrationService és run_calibration integrációs tesztek."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.db.base import Base
from app.db.models import (
    AuditEvent,
    CalibrationStatus,
    TpSlCalibration,
)
from app.db.session import AsyncSessionLocal, engine
from app.services.calibration import CalibrationService
from app.services.calibration_runner import (
    get_active_calibration_result,
    get_latest_successful_calibration,
    run_calibration,
)


class _FakeClient:
    """Tickerek + kline-ok deterministic visszaadása a kalibrációhoz."""

    def __init__(
        self,
        *,
        tickers: dict,
        klines_by_symbol: dict[str, dict],
    ) -> None:
        self._tickers = tickers
        self._klines = klines_by_symbol
        self.kline_calls: list[str] = []

    async def get_all_tickers(self) -> dict:
        return self._tickers

    async def get_klines(self, symbol: str, **kwargs) -> dict:
        self.kline_calls.append(symbol)
        return self._klines.get(symbol, {"data": []})

    async def close(self) -> None:
        pass


def _ticker_pair(symbol: str, last: str, open_p: str) -> dict:
    return {"symbol": symbol, "lastPrice": last, "open": open_p}


def _candle(o: str, h: str, low: str, c: str, t: int) -> dict:
    return {"open": o, "high": h, "low": low, "close": c, "time": t}


@pytest.fixture(scope="module", autouse=True)
def _create_schema() -> None:
    asyncio.run(_create_all())


async def _create_all() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_calibration_service_run_calibrates_top_symbols() -> None:
    """A service-nek a top-N szimbólumra kell kalibrációt készítenie."""
    tickers = {
        "data": [
            _ticker_pair("AAA", "110", "100"),  # +10%
            _ticker_pair("BBB", "60", "100"),   # -40% (top)
            _ticker_pair("CCC", "125", "100"),  # +25%
        ]
    }
    klines = {
        sym: {
            "data": [
                _candle("100", "100.5", "99.5", "100.1", 0),
                _candle("100.1", "100.6", "99.6", "100.2", 1),
                _candle("100.2", "100.7", "99.7", "100.3", 2),
                _candle("100.3", "100.8", "99.8", "100.4", 3),
            ]
        }
        for sym in ("AAA", "BBB", "CCC")
    }
    fake = _FakeClient(tickers=tickers, klines_by_symbol=klines)

    service = CalibrationService(
        client=fake,  # type: ignore[arg-type]
        lookback_minutes=10,
        top_n=2,
        tp_atr_mult=Decimal("3"),
        sl_atr_mult=Decimal("1.5"),
    )
    result = await service.run()

    assert set(result.per_symbol.keys()) == {"BBB", "CCC"}
    assert fake.kline_calls == ["BBB", "CCC"]
    for sc in result.per_symbol.values():
        assert sc.atr_pct > 0
        assert sc.tp_move_pct > sc.sl_move_pct  # R:R = 3:1.5 = 2:1
    assert result.global_tp_move_pct is not None
    assert result.global_sl_move_pct is not None


@pytest.mark.asyncio
async def test_calibration_service_returns_empty_when_no_data() -> None:
    fake = _FakeClient(tickers={"data": []}, klines_by_symbol={})
    service = CalibrationService(client=fake, top_n=5)  # type: ignore[arg-type]
    result = await service.run()
    assert result.per_symbol == {}
    assert result.global_tp_move_pct is None


@pytest.mark.asyncio
async def test_calibration_lookup_falls_back_to_global() -> None:
    tickers = {"data": [_ticker_pair("AAA", "110", "100")]}
    klines = {
        "AAA": {
            "data": [
                _candle("100", "100.5", "99.5", "100.1", 0),
                _candle("100.1", "100.6", "99.6", "100.2", 1),
            ]
        }
    }
    fake = _FakeClient(tickers=tickers, klines_by_symbol=klines)
    service = CalibrationService(client=fake, top_n=1)  # type: ignore[arg-type]
    result = await service.run()

    direct = result.lookup("AAA")
    fallback = result.lookup("UNKNOWN")
    assert direct is not None
    assert fallback is not None  # globális mediánnal pótolva
    assert fallback == (result.global_tp_move_pct, result.global_sl_move_pct)


@pytest.mark.asyncio
async def test_run_calibration_persists_row_and_audit_events(monkeypatch) -> None:
    """A run_calibration() egy SIKERES TpSlCalibration rekordot ír DB-be."""
    tickers = {"data": [_ticker_pair("AAA", "110", "100")]}
    klines = {
        "AAA": {
            "data": [
                _candle("100", "100.5", "99.5", "100.1", 0),
                _candle("100.1", "100.6", "99.6", "100.2", 1),
                _candle("100.2", "100.7", "99.7", "100.3", 2),
            ]
        }
    }
    fake = _FakeClient(tickers=tickers, klines_by_symbol=klines)

    # Monkeypatcheljük a BitunixClient konstruktort hogy a fake-et adja vissza.
    from app.services import calibration_runner as cr

    class _ClientFactory:
        def __init__(self, *args, **kwargs):
            self._wrapped = fake

        async def get_all_tickers(self):
            return await self._wrapped.get_all_tickers()

        async def get_klines(self, symbol, **kwargs):
            return await self._wrapped.get_klines(symbol, **kwargs)

        async def close(self):
            await self._wrapped.close()

    monkeypatch.setattr(cr, "BitunixClient", _ClientFactory)

    # Friss adatbázis-állapot
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(TpSlCalibration))
        await session.execute(sa.delete(AuditEvent))
        await session.commit()

    response = await run_calibration(triggered_by="unit_test")

    assert response["status"] == CalibrationStatus.SUCCESS.value
    assert response["summary"]["per_symbol"]["AAA"]["tp_move_pct"]

    async with AsyncSessionLocal() as session:
        rows = (
            (await session.execute(sa.select(TpSlCalibration))).scalars().all()
        )
        assert len(rows) == 1
        assert rows[0].status == CalibrationStatus.SUCCESS
        assert rows[0].triggered_by == "unit_test"

        events = (
            (await session.execute(sa.select(AuditEvent.event))).scalars().all()
        )
        assert "calibration.success" in events


@pytest.mark.asyncio
async def test_get_latest_returns_none_when_too_old() -> None:
    """Régi finished_at-tel rendelkező rekordot fiatalsági szűrő elhajt."""
    from datetime import UTC, datetime, timedelta

    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(TpSlCalibration))
        old = TpSlCalibration(
            status=CalibrationStatus.SUCCESS,
            triggered_by="test",
            lookback_minutes=120,
            top_n=20,
            summary={"per_symbol": {}, "global": {}},
            started_at=datetime.now(UTC) - timedelta(hours=10),
            finished_at=datetime.now(UTC) - timedelta(hours=9),
        )
        session.add(old)
        await session.commit()

        assert await get_latest_successful_calibration(session) is not None
        assert (
            await get_latest_successful_calibration(session, max_age_minutes=60)
            is None
        )
        # get_active_calibration_result is None mert default max_age 180 < 9*60
        assert await get_active_calibration_result(session) is None
