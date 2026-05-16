"""Runtime beállítások — UI control center."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import audit
from app.db.models import AuditLevel
from app.db.session import get_db
from app.schemas.settings import RuntimeSettingsPatch, TradingPauseBody
from app.schemas.trading_blackout import TradingBlackoutScheduleBody
from app.services.trading_blackout import (
    get_trading_blackout_schedule,
    set_trading_blackout_schedule,
)
from app.services.live_bus import DEFAULT_INVALIDATION_TOPICS, publish_invalidate
from app.services.runtime_settings import (
    apply_settings_patch,
    build_settings_snapshot,
    set_runtime_bool,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
async def get_settings_snapshot(
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Env + runtime effektív állapot (titkos kulcsok nélkül)."""
    return await build_settings_snapshot(session)


@router.patch("")
async def patch_settings(
    body: RuntimeSettingsPatch,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Runtime bool felülírások (DB)."""
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Legalább egy mezőt adj meg.",
        )
    try:
        applied = await apply_settings_patch(session, patch)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    await audit.record(
        session,
        "settings.runtime_patch",
        level=AuditLevel.INFO,
        message="Runtime beállítások frissítve.",
        payload={"applied": applied},
    )
    await session.commit()
    await publish_invalidate((*DEFAULT_INVALIDATION_TOPICS, "settings"))
    snap = await build_settings_snapshot(session)
    return {"applied": applied, "snapshot": snap}


@router.post("/trading-pause")
async def set_trading_pause(
    body: TradingPauseBody,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Gyors trading pause / resume."""
    await set_runtime_bool(session, "trading_paused", body.paused)
    await audit.record(
        session,
        "settings.trading_pause" if body.paused else "settings.trading_resume",
        level=AuditLevel.WARNING if body.paused else AuditLevel.INFO,
        message="Trading pause bekapcsolva." if body.paused else "Trading pause kikapcsolva.",
        payload={"trading_paused": body.paused},
    )
    await session.commit()
    await publish_invalidate(
        ("settings", "calibration", "dashboard", "strategies")
    )
    return {"trading_paused": body.paused}


@router.get("/trading-blackout")
async def get_trading_blackout(
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Heti tiltási ütemezés (új pozíció nyitás)."""
    return await get_trading_blackout_schedule(session)


@router.put("/trading-blackout")
async def put_trading_blackout(
    body: TradingBlackoutScheduleBody,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Heti tiltási ütemezés mentése."""
    try:
        saved = await set_trading_blackout_schedule(session, body.model_dump())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    await audit.record(
        session,
        "settings.trading_blackout",
        level=AuditLevel.INFO,
        message="Trading blackout ütemezés frissítve.",
        payload={"timezone": saved.get("timezone")},
    )
    await session.commit()
    await publish_invalidate((*DEFAULT_INVALIDATION_TOPICS, "settings"))
    snap = await build_settings_snapshot(session)
    return {"schedule": saved, "snapshot": snap}
