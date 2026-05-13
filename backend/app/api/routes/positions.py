"""Pozíciók végpontok."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_bitunix_client
from app.bitunix.client import BitunixClient
from app.bitunix.exceptions import BitunixAPIError, BitunixSignatureError
from app.services.positions_normalize import (
    normalize_open_positions_response,
)

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


@router.get("/normalized")
async def list_positions_normalized(
    symbol: str | None = None,
    client: BitunixClient = Depends(get_bitunix_client),
) -> dict[str, Any]:
    """Nyitott pozíciók táblázatos, frontend-barát formában.

    A nyers Bitunix válaszból parsolt mezők:
    ``symbol``, ``side``, ``qty``, ``leverage``, ``entry_price``, ``mark_price``,
    ``margin``, ``realized_pnl``, ``unrealized_pnl``, ``roi_pct``, ``liq_price``,
    ``opened_at``, ``position_id``, ``margin_mode``, ``position_mode``.

    Aggregátumok a ``totals`` mezőben: össz unrealized PnL, össz margin,
    pozíciók száma — egyszerű KPI-khez.
    """
    try:
        raw = await client.get_positions(symbol=symbol)
    except BitunixSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    except BitunixAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return normalize_open_positions_response(raw)
