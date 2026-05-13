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
    lookback_days: int = Query(
        7,
        ge=1,
        le=90,
        description=(
            "Hány napra visszamenőleg számoljuk a lezárt pozíciók KPI-jait "
            "(realized PnL, win-rate, top winners/losers)."
        ),
    ),
    session: AsyncSession = Depends(get_db),
    client: BitunixClient = Depends(get_bitunix_client),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Aggregált dashboard adatok (DB + Bitunix szinkron).

    Ha a Bitunix API kulcs nincs konfigurálva, a Bitunix-szinkron rész
    üresen tér vissza ``sync_error`` jelzéssel — a DB-alapú aggregátumok
    továbbra is működnek.
    """
    bitunix = (
        client if (settings.bitunix_api_key and settings.bitunix_api_secret) else None
    )
    return await build_dashboard_summary(
        session, bitunix, lookback_days=lookback_days
    )
