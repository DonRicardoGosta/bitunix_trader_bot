"""Health check végpont."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Egyszerű élő állapot ellenőrzés."""
    return {"status": "ok"}


@router.get("/health/db")
async def health_db(session: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """DB kapcsolat ellenőrzés."""
    await session.execute(text("SELECT 1"))
    return {"status": "ok", "component": "database"}
