"""Bitunix kliens példányosítás runtime (DB) live_trading értékkel."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.bitunix.client import BitunixClient
from app.config import Settings, get_settings
from app.services.runtime_settings import effective_live_trading


async def create_bitunix_client(
    session: AsyncSession,
    *,
    settings: Settings | None = None,
) -> BitunixClient:
    """Új kliens; a live/dry-run a DB runtime beállításból jön (env csak fallback)."""
    cfg = settings or get_settings()
    live = await effective_live_trading(session, cfg)
    return BitunixClient(
        api_key=cfg.bitunix_api_key,
        api_secret=cfg.bitunix_api_secret,
        base_url=cfg.bitunix_rest_base_url,
        live_trading=live,
    )
