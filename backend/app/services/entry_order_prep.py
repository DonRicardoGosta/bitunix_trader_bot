"""Új pozíció (OPEN) előkészítése: leverage + TP/SL (teljes pozíció)."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.bitunix.client import BitunixClient
from app.config import Settings, get_settings
from app.schemas.trading import OrderRequest
from app.services.calibration_runner import get_active_calibration_result
from app.services.order_enrichment import (
    _extract_order_list,
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


def _position_tpsl_poll_settings(
    settings: Settings | None = None,
) -> tuple[int, float]:
    cfg = settings or get_settings()
    attempts = max(1, int(getattr(cfg, "position_tpsl_resolve_max_attempts", 40)))
    delay = float(getattr(cfg, "position_tpsl_resolve_delay_seconds", 0.5))
    return attempts, delay


def position_id_from_place_order_response(
    place_order_response: dict[str, Any] | None,
) -> str | None:
    """``place_order`` válaszból ``positionId`` (ha a tőzsde visszaadja)."""
    if not isinstance(place_order_response, dict):
        return None
    data = place_order_response.get("data")
    if isinstance(data, dict):
        for key in ("positionId", "position_id"):
            val = data.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
    for key in ("positionId", "position_id"):
        val = place_order_response.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


def position_id_from_history_order_row(row: dict[str, Any]) -> str | None:
    for key in ("positionId", "position_id"):
        val = row.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


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
    side_u = order_side.upper()
    candidates: list[str] = []
    for key in ("side", "positionSide", "holdSide", "hold_side"):
        raw = row.get(key)
        if raw is not None and str(raw).strip():
            candidates.append(str(raw).upper())
    if not candidates:
        return True
    for row_side in candidates:
        if row_side == side_u:
            return True
        if row_side in ("LONG", "2", "BUY") and side_u == "BUY":
            return True
        if row_side in ("SHORT", "1", "SELL") and side_u == "SELL":
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


def _pick_position_row(
    rows: list[dict[str, Any]],
    *,
    symbol: str,
    side: str,
) -> dict[str, Any] | None:
    sym = symbol.upper()
    matching: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("symbol", sym)).upper() != sym:
            continue
        if not _position_has_size(row):
            continue
        if not _position_side_matches(row, side):
            continue
        matching.append(row)
    if len(matching) == 1:
        return matching[0]
    if not matching:
        sized: list[dict[str, Any]] = []
        for row in rows:
            if str(row.get("symbol", sym)).upper() != sym:
                continue
            if not _position_has_size(row):
                continue
            sized.append(row)
        if len(sized) == 1:
            return sized[0]
        return None
    return matching[0]


async def _wait_entry_order_history_row(
    client: BitunixClient,
    *,
    symbol: str,
    client_order_id: str,
    max_attempts: int,
    delay_seconds: float,
) -> dict[str, Any] | None:
    """Belépő rendelés history sora (fill vagy végleges állapot)."""
    sym = symbol.upper()
    for _ in range(max_attempts):
        try:
            raw = await client.get_history_orders(
                symbol=sym,
                client_id=client_order_id,
                limit=10,
            )
        except Exception:
            await asyncio.sleep(delay_seconds)
            continue
        for row in _extract_order_list(raw):
            cid = row.get("clientId") or row.get("clientOrderId") or row.get(
                "client_order_id"
            )
            if cid is None or str(cid) != client_order_id:
                continue
            st = str(row.get("status", "")).upper()
            if "FILLED" in st or "PARTIALLY" in st:
                return row
            if st in (
                "CANCELED",
                "CANCELLED",
                "REJECTED",
                "EXPIRED",
                "FAILED",
                "FAIL",
            ):
                return row
        await asyncio.sleep(delay_seconds)
    return None


def position_qty_from_row(row: dict[str, Any]) -> Decimal:
    """Nyitott pozíció méret a Bitunix pozíciósorból (abszolút érték)."""
    sym = str(row.get("symbol", "")).upper() or "?"
    for key in (
        "qty",
        "positionAmt",
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
            qty = Decimal(str(val))
        except Exception:
            continue
        if qty != 0:
            return abs(qty)
    raise OpenEntryPreparationError(f"Pozíció mérete nem olvasható: {sym}")


async def _resolve_open_position_row(
    client: BitunixClient,
    *,
    symbol: str,
    side: str,
    client_order_id: str | None = None,
    place_order_response: dict[str, Any] | None = None,
    max_attempts: int | None = None,
    delay_seconds: float | None = None,
) -> dict[str, Any]:
    """Nyitott pozíció sor a tőzsdén (TP/SL attach vagy CLOSE mennyiséghez)."""
    settings = get_settings()
    default_attempts, default_delay = _position_tpsl_poll_settings(settings)
    attempts = max_attempts if max_attempts is not None else default_attempts
    pause = delay_seconds if delay_seconds is not None else default_delay

    sym = symbol.upper()
    from_response = position_id_from_place_order_response(place_order_response)
    if from_response:
        return {"symbol": sym, "positionId": from_response}

    history_row: dict[str, Any] | None = None
    if client_order_id:
        history_row = await _wait_entry_order_history_row(
            client,
            symbol=sym,
            client_order_id=client_order_id,
            max_attempts=min(attempts, 20),
            delay_seconds=pause,
        )
        if history_row is not None:
            st = str(history_row.get("status", "")).upper()
            if st in (
                "CANCELED",
                "CANCELLED",
                "REJECTED",
                "EXPIRED",
                "FAILED",
                "FAIL",
            ):
                raise OpenEntryPreparationError(
                    f"Belépő rendelés nem töltött (állapot: {st}): {sym} {side}"
                )
            pid_hist = position_id_from_history_order_row(history_row)
            if pid_hist:
                return {"symbol": sym, "positionId": pid_hist}

    for attempt in range(attempts):
        raw = await client.get_positions(symbol=sym)
        rows = extract_open_position_rows(raw)
        picked = _pick_position_row(rows, symbol=sym, side=side)
        if picked is not None:
            pid = picked.get("positionId") or picked.get("position_id")
            if pid is not None:
                return picked
        if attempt + 1 < attempts:
            await asyncio.sleep(pause)

    detail = f"{sym} {side}"
    if client_order_id:
        detail += f" (client_order_id={client_order_id})"
    raise OpenEntryPreparationError(
        f"Nyitott pozíció nem található TP/SL rögzítéshez: {detail}"
    )


async def resolve_open_position_id(
    client: BitunixClient,
    *,
    symbol: str,
    side: str,
    client_order_id: str | None = None,
    place_order_response: dict[str, Any] | None = None,
    max_attempts: int | None = None,
    delay_seconds: float | None = None,
) -> str:
    """Nyitott pozíció ``positionId`` a belépő fill után (TP/SL position attach)."""
    row = await _resolve_open_position_row(
        client,
        symbol=symbol,
        side=side,
        client_order_id=client_order_id,
        place_order_response=place_order_response,
        max_attempts=max_attempts,
        delay_seconds=delay_seconds,
    )
    pid = row.get("positionId") or row.get("position_id")
    if pid is not None:
        return str(pid)
    raise OpenEntryPreparationError(
        f"Nyitott pozíció nem található TP/SL rögzítéshez: {symbol.upper()} {side}"
    )


async def resolve_open_position_for_exit(
    client: BitunixClient,
    *,
    symbol: str,
    side: str,
    max_attempts: int | None = None,
    delay_seconds: float | None = None,
) -> tuple[str, Decimal]:
    """Nyitott pozíció azonosító + tényleges méret hold-window CLOSE-hoz."""
    row = await _resolve_open_position_row(
        client,
        symbol=symbol,
        side=side,
        max_attempts=max_attempts,
        delay_seconds=delay_seconds,
    )
    pid = row.get("positionId") or row.get("position_id")
    if pid is None:
        sym = symbol.upper()
        raise OpenEntryPreparationError(
            f"Nyitott pozíció nem található TP/SL rögzítéshez: {sym} {side}"
        )
    return str(pid), position_qty_from_row(row)


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
    client_order_id: str | None = None,
    place_order_response: dict[str, Any] | None = None,
) -> dict:
    """Position-szintű (teljes) TP/SL a Bitunix ``tpsl/position/place_order`` API-n."""
    if dry_run_entry:
        position_id = "dry-run-position"
    else:
        position_id = await resolve_open_position_id(
            client,
            symbol=symbol,
            side=side,
            client_order_id=client_order_id,
            place_order_response=place_order_response,
        )
    return await client.place_position_tp_sl_order(
        symbol=symbol.upper(),
        position_id=position_id,
        tp_price=tp_price,
        sl_price=sl_price,
        tp_stop_type=tp_stop_type,
        sl_stop_type=sl_stop_type,
    )
