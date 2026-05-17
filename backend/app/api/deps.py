"""FastAPI dependency-k."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.bitunix.client import BitunixClient
from app.config import Settings, get_settings
from app.db.session import get_db
from app.services.bitunix_client_factory import create_bitunix_client
from app.services.trading import TradingService


async def get_bitunix_client(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AsyncIterator[BitunixClient]:
    """Per-request Bitunix kliens (live_trading a DB runtime-ból)."""
    client = await create_bitunix_client(session, settings=settings)
    try:
        yield client
    finally:
        await client.close()


async def get_trading_service(
    client: BitunixClient = Depends(get_bitunix_client),
    session: AsyncSession = Depends(get_db),
) -> TradingService:
    return TradingService(client=client, session=session)
