"""Piaci adatok végpontok (public, nincs aláírás)."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bitunix_client
from app.db.session import get_db
from app.bitunix.client import BitunixClient
from app.bitunix.exceptions import BitunixAPIError
from app.schemas.coin_analyze import (
    CoinAnalyzeRequest,
    CoinAnalyzeResponse,
    MarketSymbolRow,
)
from app.schemas.trading import TickerInfo
from app.services.coin_analyze import build_coin_analysis_payload, plan_kline_interval
from app.services.hold_window import hold_window_from_strategy_config
from app.services.strategy_runtime_config import get_top_signal_entries_config
from app.services.trading_pairs_meta import index_trading_pairs

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


@router.get("/symbols", response_model=list[MarketSymbolRow])
async def list_trading_symbols(
    client: BitunixClient = Depends(get_bitunix_client),
) -> list[MarketSymbolRow]:
    """Összes futures szimbólum max. tőkeáttétellel (Bitunix ``trading_pairs``)."""
    try:
        raw = await client.get_trading_pairs()
    except BitunixAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    meta = index_trading_pairs(raw)
    return [
        MarketSymbolRow(symbol=sym, max_leverage=m.max_leverage)
        for sym, m in sorted(meta.items(), key=lambda x: x[0])
    ]


@router.post("/coin-analyze", response_model=CoinAnalyzeResponse)
async def coin_analyze(
    body: CoinAnalyzeRequest,
    client: BitunixClient = Depends(get_bitunix_client),
    session: AsyncSession = Depends(get_db),
) -> CoinAnalyzeResponse:
    """Kline + swing elemzés egy szimbólumra (lookback → intervallum automatikus)."""
    try:
        raw_pairs = await client.get_trading_pairs()
    except BitunixAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    meta = index_trading_pairs(raw_pairs)
    pair = meta.get(body.symbol)
    if pair is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ismeretlen szimbólum: {body.symbol}",
        )

    interval, limit = plan_kline_interval(body.lookback_minutes)
    try:
        raw_klines = await client.get_klines(
            body.symbol,
            interval=interval,
            limit=limit,
        )
    except BitunixAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    tse_cfg = await get_top_signal_entries_config(session)
    hold_params = hold_window_from_strategy_config(tse_cfg)

    payload = build_coin_analysis_payload(
        symbol=body.symbol,
        max_leverage=max(1, int(pair.max_leverage)),
        lookback_minutes=body.lookback_minutes,
        interval=interval,
        kline_limit=limit,
        klines_raw=raw_klines,
        walk_forward_cooldown_minutes=body.walk_forward_cooldown_minutes,
        hold_params=hold_params,
    )
    if not payload["candles"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Nincs elegendő kline adat az elemzéshez.",
        )
    return CoinAnalyzeResponse.model_validate(payload)
