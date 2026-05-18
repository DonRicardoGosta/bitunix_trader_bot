"""Bitunix pozíció válasz normalizálása frontend-barát formára.

A nyers ``get_pending_positions`` válaszban a mezőnevek inkonzisztensek
(``positionAmt`` / ``qty`` / ``holdVol``, ``avgOpenPrice`` / ``entryPrice``).
Itt egy stabil sémát építünk a frontendnek, és pár aggregátumot is
kiszámolunk (összes unrealized PnL, össz margin, pozíciók száma).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.services.order_enrichment import (
    extract_open_position_rows,
    position_row_is_closed,
)


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _pick(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        if k in row and row[k] is not None and row[k] != "":
            return row[k]
    return None


def _ms_iso(value: Any) -> str | None:
    ms = _int(value)
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000.0, tz=UTC).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _str_or_none(v: Decimal | None) -> str | None:
    return str(v) if v is not None else None


def normalize_position_row(row: dict[str, Any]) -> dict[str, Any]:
    """Egy Bitunix pozíció sor normalizálása frontend-barát alakra."""
    qty = _dec(_pick(row, ("qty", "positionAmt", "holdVol", "size", "positionQty")))
    entry = _dec(_pick(row, ("avgOpenPrice", "entryPrice", "openPrice", "avgEntryPrice")))
    margin = _dec(_pick(row, ("margin", "positionMargin", "marginUsdt", "isolatedMargin")))
    mark = _dec(_pick(row, ("markPrice", "marketPrice", "lastPrice")))
    realized = _dec(_pick(row, ("realizedPNL", "realizedPnl", "realizedProfit"))) or Decimal(0)
    unrealized = (
        _dec(_pick(row, ("unrealizedPNL", "unrealizedPnl", "unRealizedPNL")))
        or Decimal(0)
    )
    leverage = _int(_pick(row, ("leverage",)))
    side = (_pick(row, ("side", "positionSide")) or "").upper() or None
    pos_id = _pick(row, ("positionId", "position_id"))
    margin_mode = _pick(row, ("marginMode", "margin_mode"))
    position_mode = _pick(row, ("positionMode", "position_mode"))
    liq = _dec(_pick(row, ("liqPrice", "liquidationPrice")))
    opened_ms = _pick(row, ("ctime", "openTime", "createTime", "open_time", "createdAt"))
    closed_ms = _pick(
        row,
        ("closeTime", "close_time", "uTime", "utime", "endTime", "end_time"),
    )
    updated_ms = _pick(row, ("mtime", "updateTime")) or closed_ms
    symbol = (_pick(row, ("symbol", "symbolName")) or "").upper() or None

    is_closed = position_row_is_closed(row)
    roi_pct: Decimal | None = None
    pnl_total = realized if is_closed else realized + unrealized
    if margin is not None and margin > 0:
        roi_pct = (pnl_total / margin) * Decimal(100)

    return {
        "symbol": symbol,
        "side": side,
        "qty": _str_or_none(qty),
        "entry_price": _str_or_none(entry),
        "mark_price": _str_or_none(mark),
        "leverage": leverage,
        "margin": _str_or_none(margin),
        "realized_pnl": _str_or_none(realized),
        "unrealized_pnl": _str_or_none(unrealized),
        "roi_pct": (
            str(roi_pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            if roi_pct is not None
            else None
        ),
        "liq_price": _str_or_none(liq),
        "position_id": str(pos_id) if pos_id is not None else None,
        "margin_mode": margin_mode,
        "position_mode": position_mode,
        "opened_at": _ms_iso(opened_ms),
        "closed_at": _ms_iso(closed_ms),
        "updated_at": _ms_iso(updated_ms),
    }


def normalize_open_positions_response(raw: dict[str, Any]) -> dict[str, Any]:
    """Lista + ``totals`` aggregátum a frontendnek.

    ``totals``: ``count``, ``unrealized_pnl_usdt``, ``realized_pnl_usdt``,
    ``margin_usdt`` — minden Decimal stringként.
    """
    open_raw = [
        r for r in extract_open_position_rows(raw) if not position_row_is_closed(r)
    ]
    rows = [normalize_position_row(r) for r in open_raw]
    sum_unrealized = sum(
        (Decimal(r["unrealized_pnl"]) for r in rows if r["unrealized_pnl"] is not None),
        Decimal(0),
    )
    sum_realized = sum(
        (Decimal(r["realized_pnl"]) for r in rows if r["realized_pnl"] is not None),
        Decimal(0),
    )
    sum_margin = sum(
        (Decimal(r["margin"]) for r in rows if r["margin"] is not None),
        Decimal(0),
    )
    return {
        "positions": rows,
        "totals": {
            "count": len(rows),
            "unrealized_pnl_usdt": str(sum_unrealized),
            "realized_pnl_usdt": str(sum_realized),
            "margin_usdt": str(sum_margin),
        },
    }
