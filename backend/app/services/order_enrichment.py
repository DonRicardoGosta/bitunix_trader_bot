"""Rendelés lista gazdagítása Bitunix history + nyitott pozíció alapján."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.db.models import Order


def _extract_order_list(resp: dict[str, Any]) -> list[dict[str, Any]]:
    data = resp.get("data") if isinstance(resp, dict) else None
    if not isinstance(data, dict):
        return []
    raw = data.get("orderList") or data.get("list") or []
    return raw if isinstance(raw, list) else []


def _extract_position_rows(resp: dict[str, Any]) -> list[dict[str, Any]]:
    data = resp.get("data") if isinstance(resp, dict) else None
    if data is None:
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("positionList", "list", "positions", "data"):
            raw = data.get(key)
            if isinstance(raw, list):
                return [x for x in raw if isinstance(x, dict)]
    return []


def parse_open_symbols_from_positions(raw: dict[str, Any] | None) -> set[str]:
    """Nem nulla méretű pozíciók szimbólumai (ONE_WAY-hez elég a szimbólum)."""
    out: set[str] = set()
    if raw is None:
        return out
    for row in _extract_position_rows(raw):
        sym = row.get("symbol") or row.get("symbolName")
        if not sym:
            continue
        for key in (
            "positionAmt",
            "qty",
            "positionQty",
            "holdVol",
            "size",
            "volume",
            "positionSize",
        ):
            val = row.get(key)
            if val is None:
                continue
            try:
                amt = Decimal(str(val))
            except Exception:
                continue
            if amt != 0:
                out.add(str(sym).upper())
                break
    return out


def _mtime_ms(row: dict[str, Any]) -> int:
    for k in ("mtime", "ctime", "uTime", "updateTime"):
        v = row.get(k)
        if v is None:
            continue
        try:
            return int(v)
        except (TypeError, ValueError):
            continue
    return 0


def index_history_orders_by_client_id(resp: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Ugyanazon clientId többször előfordulhat — a legfrissebb mtime marad."""
    idx: dict[str, dict[str, Any]] = {}
    for row in _extract_order_list(resp):
        cid = row.get("clientId") or row.get("client_id")
        if not cid or not isinstance(cid, str):
            continue
        prev = idx.get(cid)
        if prev is None or _mtime_ms(row) >= _mtime_ms(prev):
            idx[cid] = row
    return idx


def _dec(val: object | None) -> Decimal | None:
    if val is None or val == "":
        return None
    try:
        return Decimal(str(val))
    except Exception:
        return None


def margin_usdt_linear(
    *, qty: Decimal, price: Decimal, leverage: int
) -> Decimal | None:
    if leverage <= 0 or qty <= 0 or price <= 0:
        return None
    return (qty * price) / Decimal(leverage)


def build_order_api_dict(
    o: Order,
    *,
    hist_row: dict[str, Any] | None,
    open_symbols: set[str],
    sync_error: str | None = None,
) -> dict[str, Any]:
    """Egy Order ORM → API listaelem (HU mezők a frontendnek)."""
    sym_u = o.symbol.upper()
    exchange_status = None
    if hist_row is not None:
        exchange_status = hist_row.get("status")

    realized = _dec(hist_row.get("realizedPNL") if hist_row else None)

    qty_hist = _dec(
        (hist_row.get("tradeQty") if hist_row else None)
        or (hist_row.get("qty") if hist_row else None)
    )
    qty = qty_hist if qty_hist is not None and qty_hist > 0 else o.quantity

    price_hist = _dec(hist_row.get("price") if hist_row else None)
    price = price_hist if price_hist is not None and price_hist > 0 else o.price

    lev = o.leverage
    if hist_row and hist_row.get("leverage") is not None:
        try:
            lev = int(hist_row.get("leverage"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            lev = o.leverage

    margin = margin_usdt_linear(qty=qty, price=price or Decimal(0), leverage=lev)

    roi_pct: Decimal | None = None
    if margin is not None and margin > 0 and realized is not None:
        roi_pct = (realized / margin) * Decimal(100)

    if sym_u in open_symbols:
        lifecycle = "open"
        lifecycle_label = "Nyitott pozíció"
    elif hist_row is None:
        lifecycle = "unknown"
        lifecycle_label = "Nincs tőzsdei előzmény (clientId)"
    else:
        st = str(exchange_status or "").upper()
        if "CANCEL" in st:
            lifecycle = "canceled"
            lifecycle_label = "Visszavonva / törölve"
        elif ("FILLED" in st and "PART" not in st) or (
            realized is not None and realized != 0 and sym_u not in open_symbols
        ):
            lifecycle = "closed"
            lifecycle_label = "Lezárva"
        elif "PART" in st or "PARTIAL" in st:
            lifecycle = "partial"
            lifecycle_label = "Részben teljesült"
        elif st in ("NEW", "INIT", "PENDING") or "NEW" in st:
            lifecycle = "pending"
            lifecycle_label = "Függőben"
        else:
            lifecycle = "unknown"
            lifecycle_label = st or "Ismeretlen"

    return {
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
        "exchange": {
            "synced": sync_error is None,
            "sync_error": sync_error,
            "order_status": exchange_status,
            "lifecycle": lifecycle,
            "lifecycle_label": lifecycle_label,
            "realized_pnl_usdt": str(realized) if realized is not None else None,
            "roi_pct": (
                str(roi_pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                if roi_pct is not None
                else None
            ),
            "margin_usdt_estimate": (
                str(margin.quantize(Decimal("0.0001"))) if margin is not None else None
            ),
        },
    }
