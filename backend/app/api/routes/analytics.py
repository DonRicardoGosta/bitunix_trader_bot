"""Analytics végpontok — idősorok, ablakos statisztikák."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bitunix_client
from app.bitunix.client import BitunixClient
from app.config import Settings, get_settings
from app.db.session import get_db
from app.services.analytics import (
    build_analytics_summary,
    build_orders_window_stats,
    build_pnl_series,
    build_strategy_runs_window_stats,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary")
async def analytics_summary(
    lookback_hours: int = Query(24, ge=1, le=2160, description="Visszatekintés órában"),
    bucket_hours: int = Query(1, ge=1, le=168, description="PnL bucket méret órában"),
    session: AsyncSession = Depends(get_db),
    client: BitunixClient = Depends(get_bitunix_client),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Teljes analytics csomag egy hívásban (PnL, DB, bontások)."""
    bitunix = (
        client if (settings.bitunix_api_key and settings.bitunix_api_secret) else None
    )
    return await build_analytics_summary(
        session,
        bitunix,
        lookback_hours=lookback_hours,
        bucket_hours=bucket_hours,
    )


@router.get("/pnl-series")
async def pnl_series(
    lookback_hours: int = Query(24, ge=1, le=2160, description="Visszatekintés órában"),
    bucket_hours: int = Query(1, ge=1, le=168, description="Bucket méret órában"),
    client: BitunixClient = Depends(get_bitunix_client),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Lezárt pozíciók realized PnL idősora + KPI-k."""
    bitunix = (
        client if (settings.bitunix_api_key and settings.bitunix_api_secret) else None
    )
    return await build_pnl_series(
        bitunix, lookback_hours=lookback_hours, bucket_hours=bucket_hours
    )


@router.get("/orders")
async def orders_window(
    lookback_hours: int = Query(24, ge=1, le=2160),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await build_orders_window_stats(session, lookback_hours=lookback_hours)


@router.get("/strategy-runs")
async def strategy_runs_window(
    lookback_hours: int = Query(24, ge=1, le=2160),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await build_strategy_runs_window_stats(
        session, lookback_hours=lookback_hours
    )
