"""Kalibrációs végpontok."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import TpSlCalibration
from app.db.session import get_db
from app.services.calibration_runner import (
    get_latest_successful_calibration,
    run_calibration,
    seconds_until_next_half_hour,
)
from app.services.calibration_symbol_runs import (
    count_symbol_runs,
    list_symbol_history,
    list_symbol_runs_for_calibration,
    resolve_symbol_runs_calibration_id,
    symbol_run_to_dict,
)
from app.services.runtime_settings import effective_require_calibration, is_trading_paused
from app.services.trading_gate import is_calibration_trading_allowed

router = APIRouter(prefix="/calibration", tags=["calibration"])


def _row_to_dict(row: TpSlCalibration) -> dict:
    return {
        "id": row.id,
        "status": row.status.value if row.status else None,
        "triggered_by": row.triggered_by,
        "lookback_minutes": row.lookback_minutes,
        "top_n": row.top_n,
        "summary": row.summary,
        "error": row.error,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


@router.get("/latest")
async def get_latest(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """A legutóbbi futás állapota + trading_enabled flag."""
    max_age = max(
        settings.calibration_interval_seconds * 2 // 60,
        settings.calibration_max_age_minutes,
    )

    latest_any_stmt = (
        sa.select(TpSlCalibration)
        .order_by(TpSlCalibration.started_at.desc())
        .limit(1)
    )
    latest_any = (await session.execute(latest_any_stmt)).scalar_one_or_none()
    latest_success = await get_latest_successful_calibration(
        session, max_age_minutes=max_age
    )

    cal_allowed = await is_calibration_trading_allowed(session, settings)
    paused = await is_trading_paused(session)
    trading_enabled = cal_allowed and not paused
    require_cal = await effective_require_calibration(session, settings)

    next_run_after = (
        datetime.now(UTC) + timedelta(seconds=seconds_until_next_half_hour())
    ).isoformat()

    symbol_runs_calibration_id = resolve_symbol_runs_calibration_id(
        latest_any, latest_success
    )
    symbol_runs_persisted = 0
    if symbol_runs_calibration_id is not None:
        symbol_runs_persisted = await count_symbol_runs(
            session, symbol_runs_calibration_id
        )

    return {
        "trading_enabled": trading_enabled,
        "trading_paused": paused,
        "calibration_gate_open": cal_allowed,
        "require_calibration_for_trading": require_cal,
        "max_age_minutes": max_age,
        "now": datetime.now(UTC).isoformat(),
        "next_run_after": next_run_after,
        "symbol_runs_calibration_id": symbol_runs_calibration_id,
        "symbol_runs_persisted": symbol_runs_persisted,
        "latest": _row_to_dict(latest_any) if latest_any else None,
        "latest_successful": (
            _row_to_dict(latest_success) if latest_success else None
        ),
    }


@router.get("/runs")
async def list_runs(
    limit: int = 20,
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Kalibráció futások listája időrendi csökkenő."""
    stmt = (
        sa.select(TpSlCalibration)
        .order_by(TpSlCalibration.started_at.desc())
        .limit(max(1, min(limit, 200)))
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_row_to_dict(r) for r in rows]


@router.get("/runs/{calibration_id}/symbols")
async def list_run_symbols(
    calibration_id: int,
    symbol: str | None = None,
    qualified_only: bool | None = None,
    order_by: str = "scan_rank",
    limit: int = 200,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Egy kalibráció összes coin backtest sorai (lapozva, indexelt mezők)."""
    cal = await session.get(TpSlCalibration, calibration_id)
    if cal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"calibration {calibration_id} not found",
        )
    rows, total = await list_symbol_runs_for_calibration(
        session,
        calibration_id,
        symbol=symbol,
        qualified_only=qualified_only,
        limit=limit,
        offset=offset,
        order_by=order_by,
    )
    return {
        "calibration_id": calibration_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [symbol_run_to_dict(r) for r in rows],
    }


@router.get("/symbols/{symbol}/history")
async def symbol_calibration_history(
    symbol: str,
    limit: int = 20,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Szimbólum backtest előzményei kalibrációk között (visszakövethetőség)."""
    rows = await list_symbol_history(session, symbol, limit=limit)
    return {
        "symbol": symbol.upper(),
        "items": [symbol_run_to_dict(r) for r in rows],
    }


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def trigger_run(background: BackgroundTasks) -> dict:
    """Kézi kalibrációs futás indítása (háttérben)."""
    background.add_task(run_calibration, triggered_by="manual")
    return {"queued": True, "triggered_by": "manual"}