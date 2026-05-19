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
from app.services.calibration_symbol_runs import (
    SymbolRunDraft,
    draft_from_evaluation,
    list_symbol_runs_for_calibration,
    max_variation_win_rate_pct,
    persist_symbol_runs,
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
