"""Pozíciók végpontok."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_bitunix_client
from app.bitunix.client import BitunixClient
from app.bitunix.exceptions import BitunixAPIError, BitunixSignatureError

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("")
async def list_positions(
    symbol: str | None = None,
    client: BitunixClient = Depends(get_bitunix_client),
) -> dict:
    """Nyitott pozíciók a Bitunixról (nyers válasz)."""
    try:
        return await client.get_positions(symbol=symbol)
    except BitunixSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    except BitunixAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
