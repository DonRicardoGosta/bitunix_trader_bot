"""FastAPI dependency-k."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.bitunix.client import BitunixClient
from app.config import Settings, get_settings
from app.db.session import get_db
from app.services.trading import TradingService


async def get_bitunix_client(
    settings: Settings = Depends(get_settings),
) -> AsyncIterator[BitunixClient]:
    """Per-request Bitunix kliens."""
    client = BitunixClient(
        api_key=settings.bitunix_api_key,
        api_secret=settings.bitunix_api_secret,
        base_url=settings.bitunix_rest_base_url,
        live_trading=settings.bitunix_live_trading,
    )
    try:
        yield client
    finally:
        await client.close()


async def get_trading_service(
    client: BitunixClient = Depends(get_bitunix_client),
    session: AsyncSession = Depends(get_db),
) -> TradingService:
    return TradingService(client=client, session=session)
