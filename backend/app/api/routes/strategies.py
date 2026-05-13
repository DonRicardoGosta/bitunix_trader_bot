"""Stratégia végpontok."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import StrategyRun
from app.db.session import get_db
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
                "enabled": _is_enabled(name, settings),
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


def _is_enabled(name: str, settings: Settings) -> bool:
    if name == "top_movers":
        return settings.strategy_top_movers_enabled
    return True


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
