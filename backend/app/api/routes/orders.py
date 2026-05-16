"""Rendelés végpontok."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_trading_service
from app.bitunix.exceptions import BitunixAPIError, BitunixSignatureError
from app.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.trading import OrderRequest, OrderResponse
from app.services.entry_order_prep import OpenEntryPreparationError
from app.services.trading import TradingService
from app.services.trading_gate import is_trading_allowed

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/pnl-totals")
async def orders_pnl_totals(
    service: TradingService = Depends(get_trading_service),
) -> dict[str, Any]:
    """Összesített PnL (USDT) a saját ``orders`` tábla összes sorára.

    A soronkénti enrichment megegyezik a ``GET /api/orders`` listával
    (Bitunix history + nyitott pozíció); az összeg a realized + unrealized
    mezők összege minden naplózott rendelésre.
    """
    return await service.orders_pnl_totals()


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def place_order(
    payload: OrderRequest,
    service: TradingService = Depends(get_trading_service),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> OrderResponse:
    """Új rendelés feladása.

    A végpont csak akkor enged tradelni, ha legalább egy friss SIKERES
    kalibráció van (``require_calibration_for_trading=true``). Dry-run
    módban (``BITUNIX_LIVE_TRADING=false``) sem kerüli el a gate-et –
    így a felület konzisztensen viselkedik élesben is.
    """
    if not await is_trading_allowed(session, settings):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Trading zárolva (pause vagy nincs friss kalibráció). "
                "Ellenőrizd a Vezérlőpultot vagy indíts kalibrációt: "
                "POST /api/calibration/run."
            ),
        )
    try:
        return await service.place_order(payload)
    except OpenEntryPreparationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
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
    limit: int = Query(50, ge=1, le=500, description="Maximum sorok száma (1–500)"),
    offset: int = Query(0, ge=0, description="Kihagyott sorok száma (lapozás)"),
    symbol: str | None = Query(
        None,
        description="Szimbólum szűrő (pl. BTCUSDT) — case-insensitive",
    ),
    debug_sync: bool = Query(
        False,
        description=(
            "Ha true: minden sor exchange.debug mezőben technikai részletek "
            "(PnL/ROI számítás hibakereséséhez; ne oszd meg nyilvánosan)."
        ),
    ),
    service: TradingService = Depends(get_trading_service),
) -> list[dict[str, Any]]:
    """Legutóbbi rendelések (saját DB + Bitunix history / nyitott pozíció)."""
    return await service.list_orders(
        limit=limit,
        offset=offset,
        symbol=symbol,
        debug_sync=debug_sync,
    )
