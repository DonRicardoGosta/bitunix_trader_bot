"""Trading engedélyezés: kalibráció + runtime pause."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.services.calibration_runner import get_latest_successful_calibration
from app.services.runtime_settings import (
    effective_require_calibration,
    is_trading_paused,
)


async def is_calibration_trading_allowed(
    session: AsyncSession, settings: Settings
) -> bool:
    """Kalibrációs gate (``trading_enabled``) — pause nélkül."""
    if not await effective_require_calibration(session, settings):
        return True
    max_age = max(
        settings.calibration_interval_seconds * 2 // 60,
        settings.calibration_max_age_minutes,
    )
    cal = await get_latest_successful_calibration(
        session, max_age_minutes=max_age
    )
    return cal is not None


async def is_trading_allowed(session: AsyncSession, settings: Settings) -> bool:
    """Manuális és stratégia order: kalibráció OK és nincs pause."""
    if await is_trading_paused(session):
        return False
    return await is_calibration_trading_allowed(session, settings)
