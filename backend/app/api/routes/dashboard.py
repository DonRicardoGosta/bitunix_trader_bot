"""Dashboard végpont — főoldali KPI-k egy aggregált válaszban."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bitunix_client
from app.bitunix.client import BitunixClient
from app.config import Settings, get_settings
from app.db.session import get_db
from app.services.dashboard import build_dashboard_summary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
async def dashboard_summary(
    lookback_hours: int | None = Query(
        None,
        ge=1,
        le=2160,
        description="Visszatekintés órában (1–2160, max ~90 nap).",
    ),
    lookback_days: int | None = Query(
        None,
        ge=1,
        le=90,
        description="Kompatibilitás: napokban (felülírja lookback_hours-t, ha megadva).",
    ),
    session: AsyncSession = Depends(get_db),
    client: BitunixClient = Depends(get_bitunix_client),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Aggregált dashboard adatok (DB + Bitunix szinkron)."""
    if lookback_days is not None:
        hours = lookback_days * 24
    elif lookback_hours is not None:
        hours = lookback_hours
    else:
        hours = 168

    bitunix = (
        client if (settings.bitunix_api_key and settings.bitunix_api_secret) else None
    )
    return await build_dashboard_summary(session, bitunix, lookback_hours=hours)
