"""Rendelés végpontok."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_trading_service
from app.bitunix.exceptions import BitunixAPIError, BitunixSignatureError
from app.schemas.trading import OrderRequest, OrderResponse
from app.services.trading import TradingService

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def place_order(
    payload: OrderRequest,
    service: TradingService = Depends(get_trading_service),
) -> OrderResponse:
    """Új rendelés feladása.

    Megjegyzés: ha ``BITUNIX_LIVE_TRADING=false`` (alapértelmezett),
    a végpont csak DB-be loggol, és dry-run választ ad vissza.
    """
    try:
        return await service.place_order(payload)
    except BitunixSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    except BitunixAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc


@router.get("")
async def list_orders(
    limit: int = 50,
    service: TradingService = Depends(get_trading_service),
) -> list[dict]:
    """Legutóbbi rendelések (saját DB)."""
    orders = await service.list_orders(limit=limit)
    return [
        {
            "id": o.id,
            "client_order_id": o.client_order_id,
            "bitunix_order_id": o.bitunix_order_id,
            "symbol": o.symbol,
            "side": o.side.value,
            "type": o.type.value,
            "quantity": str(o.quantity),
            "price": str(o.price) if o.price else None,
            "leverage": o.leverage,
            "status": o.status.value,
            "created_at": o.created_at.isoformat(),
        }
        for o in orders
    ]
