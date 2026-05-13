"""Számla információ végpontok."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_bitunix_client
from app.bitunix.client import BitunixClient
from app.bitunix.exceptions import BitunixAPIError, BitunixSignatureError

router = APIRouter(prefix="/account", tags=["account"])


@router.get("")
async def get_account(
    client: BitunixClient = Depends(get_bitunix_client),
) -> dict:
    """Számla információ (egyenlegek, marginok)."""
    try:
        return await client.get_account()
    except BitunixSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    except BitunixAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
