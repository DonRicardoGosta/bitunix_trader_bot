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
    TpSlCalibrationSymbolRun,
)
from app.db.session import AsyncSessionLocal, engine
from app.services.calibration import CalibrationService
from app.services.calibration_runner import (
    get_active_calibration_result,
    get_latest_successful_calibration,
    run_calibration,
    seconds_until_next_half_hour,
)


class _FakeClient:
    """Tickerek + kline-ok deterministic visszaadása a kalibrációhoz."""

    def __init__(
        self,
        *,
        tickers: dict,
        klines_by_symbol: dict[str, dict],
        max_leverage: str = "50",
    ) -> None:
        self._tickers = tickers
        self._klines = klines_by_symbol
        self._max_leverage = max_leverage
        self.kline_calls: list[str] = []
        self.change_leverage_calls: list[dict] = []

    async def get_all_tickers(self) -> dict:
        return self._tickers

    async def get_trading_pairs(self) -> dict:
        symbols = [
            item["symbol"]
            for item in (self._tickers.get("data") or [])
            if isinstance(item, dict) and item.get("symbol")
        ]
        return {
            "data": [
                {
                    "symbol": sym,
                    "maxLeverage": self._max_leverage,
                    "basePrecision": "3",
                    "pricePrecision": "2",
                }
                for sym in symbols
            ]
        }

    async def change_leverage(self, **kwargs) -> dict:
        self.change_leverage_calls.append(kwargs)
        return {"dryRun": True}

    async def get_klines(self, symbol: str, **kwargs) -> dict:
        self.kline_calls.append(symbol)
        return self._klines.get(symbol, {"data": []})

    async def close(self) -> None:
        pass


def _ticker_pair(symbol: str, last: str, open_p: str) -> dict:
    return {"symbol": symbol, "lastPrice": last, "open": open_p}


def _candle(o: str, h: str, low: str, c: str, t: int) -> dict:
    return {"open": o, "high": h, "low": low, "close": c, "time": t}


def test_seconds_until_next_half_hour() -> None:
    from datetime import UTC, datetime

    at_29 = datetime(2025, 1, 1, 10, 29, 0, tzinfo=UTC)
    assert 0 < seconds_until_next_half_hour(at_29) <= 120
    at_30 = datetime(2025, 1, 1, 10, 30, 0, tzinfo=UTC)
    assert seconds_until_next_half_hour(at_30) == 0.0
    at_45 = datetime(2025, 1, 1, 10, 45, 0, tzinfo=UTC)
    assert seconds_until_next_half_hour(at_45) > 2400


@pytest.fixture(scope="module", autouse=True)
def _create_schema() -> None:
    asyncio.run(_create_all())


async def _create_all() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _synth_15m_klines(n: int = 80) -> list[dict]:
    from datetime import UTC, datetime

    from app.services.calibration import parse_klines

    rows = []
    for i in range(n):
        h, m = divmod(i * 15, 60)
        dt = datetime(2025, 6, 1, h % 24, m, 0, tzinfo=UTC)
        ms = int(dt.timestamp() * 1000)
        rows.append(_candle("100", "101", "99", "100.5", ms))
    return parse_klines({"data": rows})


@pytest.fixture
def _noop_symbol_persist(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(
        "app.services.calibration.persist_symbol_run_committed",
        _noop,
    )


@pytest.mark.asyncio
async def test_calibration_service_run_calibrates_top_symbols(
    monkeypatch, _noop_symbol_persist
) -> None:
    """Top mozgók közül a backtesten átment jelöltek kerülnek per_symbol-ba."""
    from app.services import candidate_backtest as cb_mod
    from app.services import kline_fetch as kf_mod

    async def _fake_fetch(_client, symbol, **kwargs):
        return _synth_15m_klines()

    captured_leverage: list[int] = []

    def _fake_eval(_klines, **kwargs):
        if "leverage" in kwargs:
            captured_leverage.append(int(kwargs["leverage"]))
        return {
            "ok": True,
            "reason": "qualified",
            "variations": [{"meets_target": True}],
            "best_variation": {
                "label": "TP100/SL50",
                "tp_roi_pct": "100",
                "sl_roi_pct": "50",
                "resolved_tp_win_rate_pct": "85.00",
                "summary": {"total_trades": 5},
            },
        }

    monkeypatch.setattr(kf_mod, "fetch_lookback_klines", _fake_fetch)
    monkeypatch.setattr(cb_mod, "evaluate_symbol_variations", _fake_eval)

    tickers = {
        "data": [
            _ticker_pair("AAA", "110", "100"),
            _ticker_pair("BBB", "60", "100"),
            _ticker_pair("CCC", "125", "100"),
        ]
    }
    fake = _FakeClient(tickers=tickers, klines_by_symbol={})

    service = CalibrationService(
        client=fake,  # type: ignore[arg-type]
        calibration_id=1,
        lookback_minutes=10080,
        top_n=2,
        candidates_target=2,
    )
    result = await service.run()

    assert set(result.per_symbol.keys()) == {"BBB", "CCC"}
    assert result.candidates_found == 2
    for sc in result.per_symbol.values():
        assert sc.backtest_win_rate_pct is not None
        assert sc.tp_roi_pct == Decimal("100")
        assert sc.leverage == 50
    assert result.global_tp_move_pct is not None
    assert len(fake.change_leverage_calls) == 2
    assert all(c["leverage"] == 50 for c in fake.change_leverage_calls)
    assert captured_leverage == [50, 50]


@pytest.mark.asyncio
async def test_calibration_skips_symbol_without_trading_pair_meta(
    monkeypatch, _noop_symbol_persist
) -> None:
    from app.services import kline_fetch as kf_mod

    async def _fake_fetch(_client, symbol, **kwargs):
        return _synth_15m_klines()

    monkeypatch.setattr(kf_mod, "fetch_lookback_klines", _fake_fetch)

    tickers = {"data": [_ticker_pair("AAA", "110", "100")]}
    fake = _FakeClient(tickers=tickers, klines_by_symbol={})
    async def _empty_pairs() -> dict:
        return {"data": []}

    fake.get_trading_pairs = _empty_pairs  # type: ignore[method-assign]

    service = CalibrationService(
        client=fake,  # type: ignore[arg-type]
        calibration_id=1,
        top_n=1,
        candidates_target=1,
    )
    result = await service.run()
    assert result.per_symbol == {}
    assert result.failed_symbols[0]["reason"] == "no_trading_pair_metadata"
    assert fake.change_leverage_calls == []


@pytest.mark.asyncio
async def test_calibration_service_returns_empty_when_no_data(
    _noop_symbol_persist,
) -> None:
    fake = _FakeClient(tickers={"data": []}, klines_by_symbol={})
    service = CalibrationService(
        client=fake, calibration_id=1, top_n=5
    )  # type: ignore[arg-type]
    result = await service.run()
    assert result.per_symbol == {}
    assert result.global_tp_move_pct is None


@pytest.mark.asyncio
async def test_calibration_lookup_falls_back_to_global(
    monkeypatch, _noop_symbol_persist
) -> None:
    from app.services import candidate_backtest as cb_mod
    from app.services import kline_fetch as kf_mod

    async def _fake_fetch(_client, symbol, **kwargs):
        return _synth_15m_klines()

    def _fake_eval(_klines, **kwargs):
        return {
            "ok": True,
            "variations": [],
            "best_variation": {
                "label": "TP50/SL50",
                "tp_roi_pct": "50",
                "sl_roi_pct": "50",
                "resolved_tp_win_rate_pct": "80.00",
                "summary": {"total_trades": 3},
            },
        }

    monkeypatch.setattr(kf_mod, "fetch_lookback_klines", _fake_fetch)
    monkeypatch.setattr(cb_mod, "evaluate_symbol_variations", _fake_eval)

    tickers = {"data": [_ticker_pair("AAA", "110", "100")]}
    fake = _FakeClient(tickers=tickers, klines_by_symbol={})
    service = CalibrationService(
        client=fake,
        calibration_id=1,
        top_n=1,
        candidates_target=1,  # type: ignore[arg-type]
    )
    result = await service.run()

    direct = result.lookup("AAA")
    fallback = result.lookup("UNKNOWN")
    assert direct is not None
    assert fallback is not None
    assert fallback == (result.global_tp_move_pct, result.global_sl_move_pct)


@pytest.mark.asyncio
async def test_run_calibration_persists_row_and_audit_events(monkeypatch) -> None:
    """A run_calibration() egy SIKERES TpSlCalibration rekordot ír DB-be."""
    from app.services import candidate_backtest as cb_mod
    from app.services import calibration_runner as cr
    from app.services import kline_fetch as kf_mod

    async def _fake_fetch(_client, symbol, **kwargs):
        return _synth_15m_klines()

    def _fake_eval(_klines, **kwargs):
        return {
            "ok": True,
            "variations": [],
            "best_variation": {
                "label": "TP50/SL50",
                "tp_roi_pct": "50",
                "sl_roi_pct": "50",
                "resolved_tp_win_rate_pct": "90.00",
                "summary": {"total_trades": 4},
            },
        }

    monkeypatch.setattr(kf_mod, "fetch_lookback_klines", _fake_fetch)
    monkeypatch.setattr(cb_mod, "evaluate_symbol_variations", _fake_eval)

    tickers = {"data": [_ticker_pair("AAA", "110", "100")]}
    fake = _FakeClient(tickers=tickers, klines_by_symbol={})

    class _ClientFactory:
        def __init__(self, *args, **kwargs):
            self._wrapped = fake

        async def get_all_tickers(self):
            return await self._wrapped.get_all_tickers()

        async def get_trading_pairs(self):
            return await self._wrapped.get_trading_pairs()

        async def change_leverage(self, **kwargs):
            return await self._wrapped.change_leverage(**kwargs)

        async def get_positions(self):
            return {"data": []}

        async def close(self):
            await self._wrapped.close()

    async def _fake_create_client(session, *, settings=None):
        return _ClientFactory()

    monkeypatch.setattr(cr, "create_bitunix_client", _fake_create_client)

    # Friss adatbázis-állapot
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(TpSlCalibrationSymbolRun))
        await session.execute(sa.delete(TpSlCalibration))
        await session.execute(sa.delete(AuditEvent))
        await session.commit()

    response = await run_calibration(
        triggered_by="unit_test",
        candidates_target=1,
        scan_limit=5,
    )

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

        sym_rows = (
            await session.execute(sa.select(TpSlCalibrationSymbolRun))
        ).scalars().all()
        assert len(sym_rows) >= 1
        assert sym_rows[0].calibration_id == rows[0].id


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
