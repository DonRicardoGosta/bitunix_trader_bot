"""Stratégia végpontok."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import StrategyRun
from app.db.session import get_db
from app.db import audit
from app.db.models import AuditLevel
from app.schemas.strategy_config import TopSignalEntriesConfigPatch
from app.services.live_bus import DEFAULT_INVALIDATION_TOPICS, publish_invalidate
from app.services.runtime_settings import effective_live_trading, is_strategy_enabled
from app.services.strategy_runtime_config import (
    get_top_signal_entries_config,
    set_top_signal_entries_config,
)
from app.services.strategy import (
    StrategyNotFoundError,
    available_strategies,
)
from app.services.strategy.runner import run_strategy

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("")
async def list_strategies(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[dict]:
    """Regisztrált stratégiák, legutóbbi futás adataival."""
    names = available_strategies()
    out: list[dict] = []
    for name in names:
        stmt = (
            select(StrategyRun)
            .where(StrategyRun.strategy_name == name)
            .order_by(StrategyRun.started_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        last = result.scalar_one_or_none()
        out.append(
            {
                "name": name,
                "enabled": await _is_enabled(session, name, settings),
                "last_run": _run_to_dict(last) if last else None,
            }
        )
    return out


@router.get("/runs")
async def list_strategy_runs(
    strategy: str | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Futás napló (opcionálisan stratégiára szűrve)."""
    stmt = (
        select(StrategyRun)
        .order_by(StrategyRun.started_at.desc())
        .limit(limit)
    )
    if strategy:
        stmt = stmt.where(StrategyRun.strategy_name == strategy)
    result = await session.execute(stmt)
    return [_run_to_dict(r) for r in result.scalars().all()]


@router.get("/top_signal_entries/config")
async def get_top_signal_entries_strategy_config(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Stratégia paraméterek (DB + kód default) és runtime kapcsolók."""
    cfg = await get_top_signal_entries_config(session)
    return {
        "config": cfg.model_dump(),
        "enabled": await is_strategy_enabled(session, settings, "top_signal_entries"),
        "live_trading": await effective_live_trading(session, settings),
    }


@router.put("/top_signal_entries/config")
async def put_top_signal_entries_strategy_config(
    body: TopSignalEntriesConfigPatch,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Stratégia paraméterek részleges mentése."""
    saved = await set_top_signal_entries_config(session, body)
    await audit.record(
        session,
        "strategy.config.updated",
        level=AuditLevel.INFO,
        message="Top signal entries konfig frissítve.",
        payload={"keys": [k for k, v in body.model_dump().items() if v is not None]},
        strategy_name="top_signal_entries",
    )
    await session.commit()
    await publish_invalidate((*DEFAULT_INVALIDATION_TOPICS, "strategies", "settings"))
    return {"config": saved.model_dump()}


@router.post("/{name}/run", status_code=status.HTTP_202_ACCEPTED)
async def trigger_strategy(name: str) -> dict:
    """Kézi indítás (szinkron lefutás)."""
    try:
        return await run_strategy(name, triggered_by="manual")
    except StrategyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strategy not found: {exc}",
        ) from exc


async def _is_enabled(
    session: AsyncSession, name: str, settings: Settings
) -> bool:
    return await is_strategy_enabled(session, settings, name)


def _run_to_dict(run: StrategyRun) -> dict:
    return {
        "id": run.id,
        "strategy_name": run.strategy_name,
        "status": run.status.value if run.status else None,
        "triggered_by": run.triggered_by,
        "details": run.details,
        "error": run.error,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }
