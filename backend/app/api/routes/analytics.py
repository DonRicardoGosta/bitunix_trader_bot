"""Analytics végpontok — idősorok, ablakos statisztikák."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
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
from app.services.analytics_window import ResolvedAnalyticsWindow, resolve_analytics_window

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _resolved_window(
    lookback_hours: int | None = Query(
        None, ge=1, le=2160, description="Visszatekintés órában (preset ablak)"
    ),
    window_start: datetime | None = Query(
        None, description="Egyedi ablak kezdete (ISO 8601, UTC vagy offset)"
    ),
    window_end: datetime | None = Query(
        None,
        description="Egyedi ablak vége (ISO 8601). Ha nincs megadva: most (élő ablak).",
    ),
) -> ResolvedAnalyticsWindow:
    try:
        return resolve_analytics_window(
            lookback_hours=lookback_hours,
            window_start=window_start,
            window_end=window_end,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/summary")
async def analytics_summary(
    bucket_hours: int = Query(1, ge=1, le=168, description="PnL bucket méret órában"),
    window: ResolvedAnalyticsWindow = Depends(_resolved_window),
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
        window=window,
        bucket_hours=bucket_hours,
    )


@router.get("/pnl-series")
async def pnl_series(
    bucket_hours: int = Query(1, ge=1, le=168, description="Bucket méret órában"),
    window: ResolvedAnalyticsWindow = Depends(_resolved_window),
    client: BitunixClient = Depends(get_bitunix_client),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Lezárt pozíciók realized PnL idősora + KPI-k."""
    bitunix = (
        client if (settings.bitunix_api_key and settings.bitunix_api_secret) else None
    )
    return await build_pnl_series(bitunix, window=window, bucket_hours=bucket_hours)


@router.get("/orders")
async def orders_window(
    window: ResolvedAnalyticsWindow = Depends(_resolved_window),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await build_orders_window_stats(session, window=window)


@router.get("/strategy-runs")
async def strategy_runs_window(
    window: ResolvedAnalyticsWindow = Depends(_resolved_window),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await build_strategy_runs_window_stats(session, window=window)
