"""Kalibrációs végpontok."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import TpSlCalibration
from app.db.session import get_db
from app.services.calibration_runner import (
    get_latest_successful_calibration,
    run_calibration,
)

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

    trading_enabled = (
        not settings.require_calibration_for_trading
        or latest_success is not None
    )

    next_run_after = None
    if latest_any and latest_any.finished_at is not None:
        finished = latest_any.finished_at
        if finished.tzinfo is None:
            finished = finished.replace(tzinfo=UTC)
        next_run_after = (
            finished + timedelta(seconds=settings.calibration_interval_seconds)
        ).isoformat()

    return {
        "trading_enabled": trading_enabled,
        "require_calibration_for_trading": settings.require_calibration_for_trading,
        "max_age_minutes": max_age,
        "now": datetime.now(UTC).isoformat(),
        "next_run_after": next_run_after,
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


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def trigger_run(background: BackgroundTasks) -> dict:
    """Kézi kalibrációs futás indítása (háttérben)."""
    background.add_task(run_calibration, triggered_by="manual")
    return {"queued": True, "triggered_by": "manual"}