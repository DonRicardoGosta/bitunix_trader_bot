"""Piaci adatok végpontok (public, nincs aláírás)."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_bitunix_client
from app.bitunix.client import BitunixClient
from app.bitunix.exceptions import BitunixAPIError
from app.schemas.trading import TickerInfo

router = APIRouter(prefix="/market", tags=["market"])


def _to_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


@router.get("/ticker/{symbol}", response_model=TickerInfo)
async def get_ticker(
    symbol: str,
    client: BitunixClient = Depends(get_bitunix_client),
) -> TickerInfo:
    """Ticker egy szimbólumhoz, normalizált formában."""
    try:
        raw = await client.get_ticker(symbol)
    except BitunixAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    data = raw.get("data")
    item: dict = {}
    if isinstance(data, list) and data:
        item = data[0]
    elif isinstance(data, dict):
        item = data

    return TickerInfo(
        symbol=symbol,
        last_price=_to_decimal(item.get("lastPrice") or item.get("last")) or Decimal(0),
        high_24h=_to_decimal(item.get("high24h") or item.get("high")),
        low_24h=_to_decimal(item.get("low24h") or item.get("low")),
        volume_24h=_to_decimal(item.get("baseVol") or item.get("volume24h")),
    )


@router.get("/depth/{symbol}")
async def get_depth(
    symbol: str,
    limit: int = 20,
    client: BitunixClient = Depends(get_bitunix_client),
) -> dict:
    """Orderbook depth nyersen visszaadva."""
    try:
        return await client.get_depth(symbol, limit=limit)
    except BitunixAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
