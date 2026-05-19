"""Per-szimbólum kalibrációs sorok DB perzisztencia és API."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.db.base import Base
from app.db.models import (
    CalibrationStatus,
    TpSlCalibration,
    TpSlCalibrationSymbolRun,
)
from app.db.session import AsyncSessionLocal, engine
from app.services.calibration_runner import supersede_stale_running_calibrations
from app.services.calibration_symbol_runs import (
    SymbolRunDraft,
    draft_from_evaluation,
    list_symbol_runs_for_calibration,
    max_variation_win_rate_pct,
    persist_symbol_runs,
    resolve_symbol_runs_calibration_id,
)


@pytest.fixture(scope="module", autouse=True)
def _create_schema() -> None:
    asyncio.run(_create_all())


async def _create_all() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(autouse=True)
async def _clean_symbol_runs() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(TpSlCalibrationSymbolRun))
        await session.execute(sa.delete(TpSlCalibration))
        await session.commit()


def test_max_variation_win_rate_pct() -> None:
    variations = [
        {"resolved_tp_win_rate_pct": "55.00"},
        {"resolved_tp_win_rate_pct": "72.50"},
        {"resolved_tp_win_rate_pct": None},
    ]
    assert max_variation_win_rate_pct(variations) == Decimal("72.50")


@pytest.mark.asyncio
async def test_persist_and_list_symbol_runs() -> None:
    async with AsyncSessionLocal() as session:
        cal = TpSlCalibration(
            status=CalibrationStatus.SUCCESS,
            triggered_by="test",
            lookback_minutes=10080,
            top_n=3,
        )
        session.add(cal)
        await session.flush()
        cal_id = cal.id

        drafts = [
            SymbolRunDraft(
                symbol="AAAUSDT",
                scan_rank=1,
                abs_change_24h_pct=Decimal("10.5"),
                reason="no_variation_meets_target",
                is_qualified=False,
                max_win_rate_pct=Decimal("65.00"),
                variations=[{"label": "TP50/SL50"}],
            ),
            SymbolRunDraft(
                symbol="BBBUSDT",
                scan_rank=2,
                abs_change_24h_pct=Decimal("8.0"),
                reason="qualified",
                is_qualified=True,
                best_win_rate_pct=Decimal("85.00"),
                max_win_rate_pct=Decimal("85.00"),
                best_variation_label="TP100/SL50",
            ),
        ]
        n = await persist_symbol_runs(session, cal_id, drafts)
        await session.commit()
        assert n == 2

    async with AsyncSessionLocal() as session:
        qualified, total_q = await list_symbol_runs_for_calibration(
            session, cal_id, qualified_only=True
        )
        assert total_q == 1
        assert qualified[0].symbol == "BBBUSDT"

        all_rows, total = await list_symbol_runs_for_calibration(
            session, cal_id, order_by="max_win_rate"
        )
        assert total == 2
        assert all_rows[0].symbol == "BBBUSDT"


@pytest.mark.asyncio
async def test_supersede_stale_running_calibrations() -> None:
    async with AsyncSessionLocal() as session:
        old = TpSlCalibration(
            status=CalibrationStatus.RUNNING,
            triggered_by="test",
            lookback_minutes=120,
            top_n=10,
        )
        new = TpSlCalibration(
            status=CalibrationStatus.RUNNING,
            triggered_by="test",
            lookback_minutes=120,
            top_n=10,
        )
        session.add_all([old, new])
        await session.flush()
        n = await supersede_stale_running_calibrations(session, keep_id=new.id)
        await session.commit()
        assert n == 1
        await session.refresh(old)
        assert old.status == CalibrationStatus.FAILED
        assert "superseded_by_calibration" in (old.error or "")


def test_resolve_symbol_runs_calibration_id() -> None:
    running = TpSlCalibration(
        id=2,
        status=CalibrationStatus.RUNNING,
        triggered_by="t",
        lookback_minutes=1,
        top_n=1,
    )
    success = TpSlCalibration(
        id=1,
        status=CalibrationStatus.SUCCESS,
        triggered_by="t",
        lookback_minutes=1,
        top_n=1,
    )
    assert resolve_symbol_runs_calibration_id(running, success) == 2
    assert resolve_symbol_runs_calibration_id(None, success) == 1


def test_draft_from_evaluation_not_selected() -> None:
    eval_out = {
        "ok": True,
        "reason": "qualified",
        "variations": [{"resolved_tp_win_rate_pct": "90.00"}],
        "best_variation": {
            "label": "TP50/SL50",
            "tp_roi_pct": "50",
            "sl_roi_pct": "50",
            "resolved_tp_win_rate_pct": "90.00",
            "summary": {"total_trades": 10, "tp_wins": 9, "sl_losses": 1, "no_result": 0},
        },
    }
    draft = draft_from_evaluation(
        symbol="XUSDT",
        scan_rank=1,
        abs_change_24h_pct=Decimal("5"),
        kline_samples=100,
        eval_out=eval_out,
        is_selected_candidate=False,
    )
    assert draft.is_qualified is False
    assert draft.max_win_rate_pct == Decimal("90.00")
