"""Új pozíció (OPEN) előkészítése: leverage + TP/SL (teljes pozíció)."""

from __future__ import annotations

import asyncio
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.bitunix.client import BitunixClient
from app.config import Settings, get_settings
from app.schemas.trading import OrderRequest
from app.services.calibration_runner import get_active_calibration_result
from app.services.order_enrichment import (
    extract_open_position_rows,
    last_or_mark_price_from_ticker,
)
from app.services.tpsl import (
    compute_tp_sl_prices_from_move_pct,
    implied_price_move_pct_from_roi,
)
from app.services.trading_pairs_meta import index_trading_pairs


class OpenEntryPreparationError(ValueError):
    """OPEN belépés előkészítése sikertelen (hiányzó ár, TP/SL, meta)."""


async def prepare_open_entry_order(
    *,
    client: BitunixClient,
    session: AsyncSession,
    payload: OrderRequest,
    settings: Settings | None = None,
) -> OrderRequest:
    """Leverage beállítás + kötelező TP/SL, ha hiányzik – egy REST ``place_order``-hez.

    A stratégiák már küldhetnek ``tpPrice`` / ``slPrice`` értéket; a manuális API
  és a hiányos kérések a kalibráció / ROI fallback alapján töltik ki.
    """
    if payload.trade_side != "OPEN" or payload.reduce_only:
        return payload

    cfg = settings or get_settings()
    symbol = payload.symbol.upper()

    await client.change_leverage(
        symbol=symbol,
        leverage=payload.leverage,
        margin_coin=cfg.bitunix_margin_coin,
    )

    if payload.tp_price is not None and payload.sl_price is not None:
        return payload
    if (payload.tp_price is None) != (payload.sl_price is None):
        raise OpenEntryPreparationError(
            "OPEN rendelésnél a tpPrice és slPrice együtt kötelező (vagy mindkettő üres)."
        )

    entry = await _resolve_entry_price(client, payload)
    pairs_raw = await client.get_trading_pairs()
    meta = index_trading_pairs(pairs_raw).get(symbol)
    price_precision = meta.price_precision if meta else 4

    tp_move_pct, sl_move_pct = await _resolve_move_pcts(
        symbol=symbol,
        leverage=payload.leverage,
        session=session,
        settings=cfg,
    )
    tp_price, sl_price = compute_tp_sl_prices_from_move_pct(
        entry_price=entry,
        side=payload.side,
        tp_move_pct=tp_move_pct,
        sl_move_pct=sl_move_pct,
        price_precision=price_precision,
    )

    return payload.model_copy(
        update={
            "tp_price": tp_price,
            "sl_price": sl_price,
            "tp_stop_type": payload.tp_stop_type or cfg.strategy_tpsl_stop_type,
            "sl_stop_type": payload.sl_stop_type or cfg.strategy_tpsl_stop_type,
        }
    )


async def _resolve_entry_price(client: BitunixClient, payload: OrderRequest) -> Decimal:
    if payload.order_type == "LIMIT" and payload.price is not None:
        return payload.price
    raw = await client.get_ticker(payload.symbol)
    last = last_or_mark_price_from_ticker(raw)
    if last is None or last <= 0:
        raise OpenEntryPreparationError(
            f"Nem sikerült belépő árat lekérni: {payload.symbol}"
        )
    return last


async def _resolve_move_pcts(
    *,
    symbol: str,
    leverage: int,
    session: AsyncSession,
    settings: Settings,
) -> tuple[Decimal, Decimal]:
    from app.services.strategy_runtime_config import get_top_signal_entries_config

    cfg = await get_top_signal_entries_config(session)
    tp_roi = Decimal(cfg.tp_roi_pct)
    sl_roi = Decimal(cfg.sl_roi_pct)

    calibration = await get_active_calibration_result(session)
    if calibration is not None:
        moves = calibration.lookup(symbol)
        if moves is not None:
            return moves

    return implied_price_move_pct_from_roi(
        leverage=leverage,
        tp_roi_pct=tp_roi,
        sl_roi_pct=sl_roi,
    )


def _position_side_matches(row: dict, order_side: str) -> bool:
    row_side = str(row.get("side") or row.get("positionSide") or "").upper()
    if not row_side:
        return True
    side_u = order_side.upper()
    if row_side == side_u:
        return True
    if row_side in ("LONG", "2") and side_u == "BUY":
        return True
    if row_side in ("SHORT", "1") and side_u == "SELL":
        return True
    return False


def _position_has_size(row: dict) -> bool:
    for key in (
        "positionAmt",
        "qty",
        "positionQty",
        "holdVol",
        "size",
        "volume",
        "positionSize",
        "maxQty",
    ):
        val = row.get(key)
        if val is None:
            continue
        try:
            if Decimal(str(val)) != 0:
                return True
        except Exception:
            continue
    return False


async def resolve_open_position_id(
    client: BitunixClient,
    *,
    symbol: str,
    side: str,
    max_attempts: int = 12,
    delay_seconds: float = 0.25,
) -> str:
    """Nyitott pozíció ``positionId`` a belépő fill után (TP/SL position attach)."""
    sym = symbol.upper()
    for attempt in range(max_attempts):
        raw = await client.get_positions(symbol=sym)
        for row in extract_open_position_rows(raw):
            if str(row.get("symbol", sym)).upper() != sym:
                continue
            if not _position_side_matches(row, side):
                continue
            if not _position_has_size(row):
                continue
            pid = row.get("positionId") or row.get("position_id")
            if pid is not None:
                return str(pid)
        if attempt + 1 < max_attempts:
            await asyncio.sleep(delay_seconds)
    raise OpenEntryPreparationError(
        f"Nyitott pozíció nem található TP/SL rögzítéshez: {sym} {side}"
    )


async def attach_full_position_tp_sl(
    client: BitunixClient,
    *,
    symbol: str,
    side: str,
    tp_price: Decimal,
    sl_price: Decimal,
    tp_stop_type: str,
    sl_stop_type: str,
    dry_run_entry: bool,
) -> dict:
    """Position-szintű (teljes) TP/SL a Bitunix ``tpsl/position/place_order`` API-n."""
    if dry_run_entry:
        position_id = "dry-run-position"
    else:
        position_id = await resolve_open_position_id(client, symbol=symbol, side=side)
    return await client.place_position_tp_sl_order(
        symbol=symbol.upper(),
        position_id=position_id,
        tp_price=tp_price,
        sl_price=sl_price,
        tp_stop_type=tp_stop_type,
        sl_stop_type=sl_stop_type,
    )
