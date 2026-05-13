"""Rendelés lista gazdagítása Bitunix history + nyitott pozíció alapján."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.db.models import Order


@dataclass(frozen=True)
class TradeAugment:
    """Összesítés a ``get_history_trades`` sorokból (clientId / orderId szerint)."""

    realized_sum: Decimal
    avg_price: Decimal  # VWAP kitöltési ár; 0 ha nincs adat


def _bitunix_rows(
    resp: dict[str, Any] | None, *, list_keys: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Bitunix ``{code, data: ...}`` válaszból lista kinyerése (többféle alak)."""
    if not isinstance(resp, dict):
        return []
    data = resp.get("data")
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, dict):
            for key in list_keys:
                raw = inner.get(key)
                if isinstance(raw, list):
                    return [x for x in raw if isinstance(x, dict)]
        for key in list_keys:
            raw = data.get(key)
            if isinstance(raw, list):
                return [x for x in raw if isinstance(x, dict)]
    return []


def _extract_order_list(resp: dict[str, Any]) -> list[dict[str, Any]]:
    return _bitunix_rows(
        resp,
        list_keys=(
            "orderList",
            "orders",
            "order_list",
            "list",
            "rows",
            "items",
        ),
    )


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


def normalize_str_id(val: object | None) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def index_history_orders_by_client_id(resp: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Ugyanazon clientId többször előfordulhat — a legfrissebb mtime marad."""
    idx: dict[str, dict[str, Any]] = {}
    for row in _extract_order_list(resp):
        cid = normalize_str_id(
            row.get("clientId")
            or row.get("client_id")
            or row.get("clientID")
            or row.get("clOrdId")
        )
        if not cid:
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


def _extract_trade_list(resp: dict[str, Any]) -> list[dict[str, Any]]:
    return _bitunix_rows(
        resp,
        list_keys=(
            "tradeList",
            "trades",
            "trade_list",
            "list",
            "rows",
            "items",
        ),
    )


def _realized_from_row(row: dict[str, Any] | None) -> Decimal | None:
    if not row:
        return None
    for key in (
        "realizedPNL",
        "realizedPnl",
        "realizedProfit",
        "profit",
        "pnl",
        "closeProfit",
    ):
        v = _dec(row.get(key))
        if v is not None:
            return v
    return None


def _trade_qty(row: dict[str, Any]) -> Decimal | None:
    for key in ("qty", "baseVol", "quantity", "vol", "fillQty", "execQty", "size"):
        q = _dec(row.get(key))
        if q is not None and q > 0:
            return q
    return None


def _trade_price(row: dict[str, Any]) -> Decimal | None:
    for key in ("price", "tradePrice", "avgPrice", "fillPrice", "dealPrice", "execPrice"):
        p = _dec(row.get(key))
        if p is not None and p > 0:
            return p
    return None


def aggregate_trades_response(resp: dict[str, Any]) -> TradeAugment:
    """Összes trade sor összesítése (pl. ``positionId`` szűrés után)."""
    total_r = Decimal(0)
    wn = Decimal(0)
    wd = Decimal(0)
    for row in _extract_trade_list(resp):
        r = _realized_from_row(row)
        if r is not None:
            total_r += r
        q = _trade_qty(row)
        p = _trade_price(row)
        if q is not None and p is not None and q > 0 and p > 0:
            wn += q * p
            wd += q
    ap = (wn / wd) if wd > 0 else Decimal(0)
    return TradeAugment(realized_sum=total_r, avg_price=ap)


def build_trade_augment_indices(
    resp: dict[str, Any],
) -> tuple[dict[str, TradeAugment], dict[str, TradeAugment]]:
    """``(by_client_id, by_order_id)`` → VWAP ár + összesített realized PnL."""
    cr: dict[str, Decimal] = {}
    cn: dict[str, Decimal] = {}
    cd: dict[str, Decimal] = {}
    or_: dict[str, Decimal] = {}
    on: dict[str, Decimal] = {}
    od: dict[str, Decimal] = {}

    for row in _extract_trade_list(resp):
        r = _realized_from_row(row)
        r_val = r if r is not None else Decimal(0)
        q = _trade_qty(row)
        p = _trade_price(row)
        cid = normalize_str_id(
            row.get("clientId")
            or row.get("client_id")
            or row.get("clientID")
            or row.get("clOrdId")
        )
        oid = normalize_str_id(row.get("orderId") or row.get("order_id"))
        if cid:
            cr[cid] = cr.get(cid, Decimal(0)) + r_val
            if q is not None and p is not None and q > 0 and p > 0:
                cn[cid] = cn.get(cid, Decimal(0)) + q * p
                cd[cid] = cd.get(cid, Decimal(0)) + q
        if oid:
            or_[oid] = or_.get(oid, Decimal(0)) + r_val
            if q is not None and p is not None and q > 0 and p > 0:
                on[oid] = on.get(oid, Decimal(0)) + q * p
                od[oid] = od.get(oid, Decimal(0)) + q

    def _finalize(
        rs: dict[str, Decimal], ns: dict[str, Decimal], ds: dict[str, Decimal]
    ) -> dict[str, TradeAugment]:
        out: dict[str, TradeAugment] = {}
        keys = set(rs) | set(ns) | set(ds)
        for k in keys:
            ap = (ns[k] / ds[k]) if ds.get(k, Decimal(0)) > 0 else Decimal(0)
            out[k] = TradeAugment(realized_sum=rs.get(k, Decimal(0)), avg_price=ap)
        return out

    return _finalize(cr, cn, cd), _finalize(or_, on, od)


def last_or_mark_price_from_ticker(raw: dict[str, Any]) -> Decimal | None:
    """Tickers válaszból utolsó vagy mark ár (margin becsléshez)."""
    data = raw.get("data") if isinstance(raw, dict) else None
    item: dict[str, Any] = {}
    if isinstance(data, list) and data and isinstance(data[0], dict):
        item = data[0]
    elif isinstance(data, dict):
        item = data
    p = _dec(item.get("markPrice") or item.get("lastPrice") or item.get("last"))
    return p if p is not None and p > 0 else None


def _price_from_hist_row(hist_row: dict[str, Any] | None) -> Decimal | None:
    if not hist_row:
        return None
    for key in (
        "avgPrice",
        "avg_price",
        "tradePrice",
        "dealPrice",
        "fillPrice",
        "avgFillPrice",
        "price",
        "orderPrice",
    ):
        p = _dec(hist_row.get(key))
        if p is not None and p > 0:
            return p
    return None


def pick_trade_augment(
    by_client: dict[str, TradeAugment],
    by_order: dict[str, TradeAugment],
    *,
    client_order_id: str,
    bitunix_order_id: str | None,
) -> TradeAugment | None:
    cid = normalize_str_id(client_order_id) or client_order_id
    oid = normalize_str_id(bitunix_order_id)
    c = by_client.get(cid) or by_client.get(client_order_id)
    o = by_order.get(oid) if oid else None
    if c and c.avg_price > 0:
        return c
    if o and o.avg_price > 0:
        return o
    return c or o


def best_trade_augment(*parts: TradeAugment | None) -> TradeAugment | None:
    """Több forrás közül: nagyobb |realized|, majd van-e VWAP ár."""
    cand = [p for p in parts if p is not None]
    if not cand:
        return None
    return max(cand, key=lambda p: (abs(p.realized_sum), int(p.avg_price > 0)))


def earliest_history_start_ms(orders: list[Order], symbol: str) -> int | None:
    """``startTime`` Bitunixhez: a szimbólumhoz tartozó legrégebbi DB rendelés − 14 nap."""
    times = [o.created_at for o in orders if o.symbol == symbol]
    if not times:
        return None
    t = min(times)
    t = t.replace(tzinfo=UTC) if t.tzinfo is None else t.astimezone(UTC)
    return int((t - timedelta(days=14)).timestamp() * 1000)


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
    trade_augment: TradeAugment | None = None,
    mark_price: Decimal | None = None,
) -> dict[str, Any]:
    """Egy Order ORM → API listaelem (HU mezők a frontendnek)."""
    sym_u = o.symbol.upper()
    exchange_status = None
    if hist_row is not None:
        exchange_status = hist_row.get("status")

    realized_hist = _realized_from_row(hist_row) if hist_row else None
    realized: Decimal | None = realized_hist
    if trade_augment is not None and (
        trade_augment.realized_sum != 0 or realized_hist is None
    ):
        realized = trade_augment.realized_sum

    qty_hist = _dec(
        (hist_row.get("tradeQty") if hist_row else None)
        or (hist_row.get("qty") if hist_row else None)
    )
    qty = qty_hist if qty_hist is not None and qty_hist > 0 else o.quantity

    price_hist = _price_from_hist_row(hist_row)
    ta_price = (
        trade_augment.avg_price
        if trade_augment is not None and trade_augment.avg_price > 0
        else None
    )
    db_dec = _dec(o.price) if o.price is not None else None
    db_price = db_dec if db_dec is not None and db_dec > 0 else None
    mp = mark_price if mark_price is not None and mark_price > 0 else None
    price = price_hist or db_price or ta_price or mp

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
