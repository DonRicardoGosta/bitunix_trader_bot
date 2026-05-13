"""Audit események végpont."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import audit
from app.db.session import get_db

router = APIRouter(prefix="/events", tags=["events"])


@router.get("")
async def list_events(
    level: str | None = Query(default=None, description="DEBUG|INFO|WARNING|ERROR"),
    event_prefix: str | None = Query(default=None, description="pl. strategy.top_movers"),
    strategy_name: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Audit események időrendi (csökkenő) listája szűrőkkel."""
    rows = await audit.list_events(
        session,
        level=level,
        event_prefix=event_prefix,
        strategy_name=strategy_name,
        limit=limit,
    )
    return [
        {
            "id": e.id,
            "level": e.level.value if e.level else None,
            "event": e.event,
            "message": e.message,
            "payload": e.payload,
            "strategy_name": e.strategy_name,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in rows
    ]
