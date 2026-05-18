"""Rendelés lista gazdagítása Bitunix history + nyitott pozíció alapján."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.db.models import Order

# Belépő rendelés ``created_at`` és a Bitunix oldali pozíció ``ctime`` közti
# megengedett eltérés ms-ben. A saját DB rögzítési idő és a Bitunix fill idő
# között gyakran van 1-3 mp delay; ezzel a tolerancával biztos meglesz a
# párosítás, miközben két szomszédos belépőt nem keverünk össze.
POSITION_MATCH_TOLERANCE_MS = 30_000


@dataclass(frozen=True)
class TradeAugment:
    """Összesítés a ``get_history_trades`` sorokból (clientId / orderId szerint)."""

    realized_sum: Decimal
    avg_price: Decimal  # VWAP kitöltési ár; 0 ha nincs adat


@dataclass(frozen=True)
class PositionMatch:
    """Egy DB rendeléshez tartozó Bitunix pozíció PnL adatai.

    A Bitunix ``get_history_orders`` válaszában a belépő rendelésen mindig
    ``realizedPNL=0`` szerepel – a tényleges realized PnL pozíció-szinten
    érhető el (``get_pending_positions`` nyitottra, ``get_history_positions``
    lezártra). Ez a struktúra mindkettőből egységes formára hozza az adatot.

    Attributes:
        position_id: Bitunix pozíció azonosító.
        side: ``BUY`` (long) vagy ``SELL`` (short).
        is_open: True ha a pozíció még nyitott (van unrealized PnL).
        realized_pnl: Eddig realizált PnL USDT-ben (zárás vagy részleges).
        unrealized_pnl: Mark-to-market nyereség nyitott pozíción (0 ha zárt).
        margin: Foglalt fedezet USDT-ben; ``None`` ha a Bitunix nem adta vissza.
        entry_price: Pozíció átlagos belépő ára (VWAP).
        close_price: Lezárás VWAP-ja (None nyitottra).
        qty: Pozíció max. méret (kontraktusban / coin-ban).
        leverage: Tőkeáttétel.
    """

    position_id: str | None
    side: str
    is_open: bool
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    margin: Decimal | None
    entry_price: Decimal | None
    close_price: Decimal | None
    qty: Decimal | None
    leverage: int | None


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


def extract_open_position_rows(raw: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Nyers ``get_pending_positions`` válaszból a pozíciók sorai."""
    if raw is None:
        return []
    return _extract_position_rows(raw)


def extract_history_position_rows(
    raw: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Nyers ``get_history_positions`` válaszból a pozíciók sorai."""
    if raw is None:
        return []
    return _bitunix_rows(
        raw,
        list_keys=("positionList", "list", "positions", "rows", "items", "data"),
    )


def _position_ctime_ms(row: dict[str, Any]) -> int | None:
    for k in ("ctime", "createTime", "openTime", "open_time", "createdAt"):
        v = row.get(k)
        if v is None:
            continue
        try:
            return int(v)
        except (TypeError, ValueError):
            continue
    return None


def _pos_decimal(row: dict[str, Any], keys: tuple[str, ...]) -> Decimal | None:
    for k in keys:
        v = _dec(row.get(k))
        if v is not None:
            return v
    return None


def position_qty_from_row(row: dict[str, Any]) -> Decimal | None:
    """Pozíció méret a Bitunix sor többféle mezőnevéből."""
    return _pos_decimal(
        row,
        (
            "positionAmt",
            "qty",
            "positionQty",
            "holdVol",
            "size",
            "volume",
            "positionSize",
            "maxQty",
        ),
    )


def position_row_is_closed(row: dict[str, Any]) -> bool:
    """True ha a sor lezárt / nulla méretű pozíciót jelöl (pl. pending listában maradt szellem)."""
    qty = position_qty_from_row(row)
    if qty is not None and qty == 0:
        return True
    for key in ("closeTime", "close_time", "endTime", "end_time"):
        if row.get(key) not in (None, "", 0, "0"):
            return True
    status = str(row.get("status") or row.get("positionStatus") or "").upper()
    if status in ("CLOSED", "CLOSE", "LIQUIDATED", "LIQUIDATION"):
        return True
    return False


def position_id_from_row(row: dict[str, Any]) -> str | None:
    for key in ("positionId", "position_id"):
        val = row.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


def find_position_row_by_id(
    position_id: str,
    *,
    open_position_rows: list[dict[str, Any]],
    history_position_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], bool] | None:
    """``(row, from_open_list)`` — history előbb, mert pontosabb lezárt PnL-hez."""
    pid = str(position_id).strip()
    if not pid:
        return None
    for row in history_position_rows:
        if position_id_from_row(row) == pid:
            return row, False
    for row in open_position_rows:
        if position_id_from_row(row) == pid:
            return row, True
    return None


def _pos_int(row: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for k in keys:
        v = row.get(k)
        if v is None:
            continue
        try:
            return int(str(v))
        except (TypeError, ValueError):
            continue
    return None


def position_match_from_row(
    row: dict[str, Any], *, is_open: bool
) -> PositionMatch:
    """Bitunix nyers pozíció sorból ``PositionMatch``-ot épít.

    A nyitott és lezárt pozíció sorok mezőnévben kissé eltérnek
    (``avgOpenPrice`` vs ``entryPrice``, ``unrealizedPNL`` csak nyitottra),
    ez a konverzió mindkettőre működik.
    """
    realized = _pos_decimal(
        row, ("realizedPNL", "realizedPnl", "realizedProfit", "profit", "pnl")
    ) or Decimal(0)
    unrealized = (
        _pos_decimal(row, ("unrealizedPNL", "unrealizedPnl", "unRealizedPNL"))
        if is_open
        else None
    ) or Decimal(0)
    margin = _pos_decimal(row, ("margin", "positionMargin", "marginUsdt"))
    entry = _pos_decimal(row, ("avgOpenPrice", "entryPrice", "openPrice"))
    close = _pos_decimal(row, ("closePrice", "avgClosePrice"))
    qty = _pos_decimal(row, ("maxQty", "qty", "positionQty", "size"))
    leverage = _pos_int(row, ("leverage",))
    side_raw = row.get("side") or row.get("positionSide") or ""
    side = str(side_raw).upper() or "BUY"
    pid = row.get("positionId") or row.get("position_id")
    return PositionMatch(
        position_id=str(pid) if pid is not None else None,
        side=side,
        is_open=is_open,
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        margin=margin,
        entry_price=entry,
        close_price=close,
        qty=qty,
        leverage=leverage,
    )


def _order_created_at_ms(order: Order) -> int | None:
    ts = order.created_at
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return int(ts.timestamp() * 1000)


def match_position_for_order(
    order: Order,
    *,
    open_position_rows: list[dict[str, Any]],
    history_position_rows: list[dict[str, Any]],
    hint_position_id: str | None = None,
    tolerance_ms: int = POSITION_MATCH_TOLERANCE_MS,
) -> PositionMatch | None:
    """DB rendelés ↔ Bitunix pozíció párosítás.

    Stratégia: a belépő rendelés (``reduceOnly=false``) ``created_at``-je
    nagyon közel van a Bitunix oldali pozíció ``ctime``-jához (a pozíciót a
    Bitunix az entry fill-kor hozza létre). Párosítás kulcsai:

    * **symbol** (egyezőség kötelező, case-insensitive)
    * **side** (``BUY``/``SELL``, HEDGE módban két párhuzamos pozíció lehet)
    * **ctime ≈ order.created_at** (lásd ``POSITION_MATCH_TOLERANCE_MS``)

    Záró rendeléseket (``reduceOnly=true``) jelenleg nem párosítjuk pozícióhoz:
    azoknál egyébként sem hiányzik a ``realizedPNL`` a ``get_history_orders``-ból,
    úgyhogy a meglévő enrichment ott helyesen működik.
    """
    if order.reduce_only:
        return None

    if hint_position_id:
        found = find_position_row_by_id(
            hint_position_id,
            open_position_rows=open_position_rows,
            history_position_rows=history_position_rows,
        )
        if found is not None:
            row, from_open = found
            is_open = from_open and not position_row_is_closed(row)
            return position_match_from_row(row, is_open=is_open)

    order_ts = _order_created_at_ms(order)
    if order_ts is None:
        return None
    sym_u = order.symbol.upper()
    side_u = order.side.value.upper() if hasattr(order.side, "value") else str(order.side).upper()

    best: tuple[dict[str, Any], bool, int] | None = None  # (row, is_open, diff_ms)

    def _consider(row: dict[str, Any], from_open_list: bool) -> None:
        nonlocal best
        if from_open_list and position_row_is_closed(row):
            return
        if str(row.get("symbol", "")).upper() != sym_u:
            return
        row_side = str(row.get("side", "")).upper()
        if row_side and row_side != side_u:
            return
        ct = _position_ctime_ms(row)
        if ct is None:
            return
        diff = abs(ct - order_ts)
        if diff > tolerance_ms:
            return
        is_open = from_open_list and not position_row_is_closed(row)
        if best is None or diff < best[2]:
            best = (row, is_open, diff)
        elif diff == best[2] and not is_open and best[1]:
            # Ugyanaz a ctime: lezárt history előnyben a pending szellemhez képest.
            best = (row, is_open, diff)

    for row in open_position_rows:
        _consider(row, True)
    for row in history_position_rows:
        _consider(row, False)

    if best is None:
        return None
    row, is_open, _ = best
    return position_match_from_row(row, is_open=is_open)


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


HISTORY_POSITION_PAGES_PER_SYMBOL = 8


async def fetch_history_position_rows_for_symbol(
    client: Any,
    *,
    symbol: str,
    start_time_ms: int | None,
    pages: int = HISTORY_POSITION_PAGES_PER_SYMBOL,
) -> list[dict[str, Any]]:
    """Lapozott ``get_history_positions`` — több lezárt pozíció illesztéséhez."""
    out: list[dict[str, Any]] = []
    page_size = 100
    for page in range(max(1, pages)):
        raw = await client.get_history_positions(
            symbol=symbol,
            limit=page_size,
            skip=page * page_size,
            start_time_ms=start_time_ms,
        )
        rows = extract_history_position_rows(raw)
        if not rows:
            break
        out.extend(rows)
        if len(rows) < page_size:
            break
    return out


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
    position_match: PositionMatch | None = None,
    include_debug: bool = False,
    debug_extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Egy Order ORM → API listaelem (HU mezők a frontendnek).

    Args:
        position_match: Ha megvan a pozíció (akár nyitott, akár lezárt), akkor
            **ez** az elsődleges forrás a realized PnL / margin / ROI értékekhez,
            mert a Bitunix ``get_history_orders`` válaszában a belépő rendelés
            ``realizedPNL``-je definíció szerint ``0``. A trade / hist row csak
            fallback ha a pozíció nem található (pl. canceled order).
    """
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

    # A pozíció-szintű PnL a legpontosabb forrás (lásd docstring).
    unrealized: Decimal | None = None
    if position_match is not None:
        realized = position_match.realized_pnl
        if position_match.is_open:
            unrealized = position_match.unrealized_pnl

    qty_hist = _dec(
        (hist_row.get("tradeQty") if hist_row else None)
        or (hist_row.get("qty") if hist_row else None)
    )
    qty = qty_hist if qty_hist is not None and qty_hist > 0 else o.quantity
    if position_match is not None and position_match.qty is not None and position_match.qty > 0:
        qty = position_match.qty

    price_hist = _price_from_hist_row(hist_row)
    ta_price = (
        trade_augment.avg_price
        if trade_augment is not None and trade_augment.avg_price > 0
        else None
    )
    db_dec = _dec(o.price) if o.price is not None else None
    db_price = db_dec if db_dec is not None and db_dec > 0 else None
    mp = mark_price if mark_price is not None and mark_price > 0 else None
    pos_entry = (
        position_match.entry_price
        if position_match is not None
        and position_match.entry_price is not None
        and position_match.entry_price > 0
        else None
    )
    price = pos_entry or price_hist or db_price or ta_price or mp

    lev = o.leverage
    if position_match is not None and position_match.leverage:
        lev = position_match.leverage
    elif hist_row and hist_row.get("leverage") is not None:
        try:
            lev = int(hist_row.get("leverage"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            lev = o.leverage

    margin = (
        position_match.margin
        if position_match is not None
        and position_match.margin is not None
        and position_match.margin > 0
        else margin_usdt_linear(qty=qty, price=price or Decimal(0), leverage=lev)
    )

    # ROI az aktuális Bitunix UI logikát követi:
    #  * nyitott pozíció  → (realized + unrealized) / margin
    #  * lezárt pozíció   → realized / margin
    roi_basis: Decimal | None = None
    if realized is not None:
        roi_basis = realized + (unrealized if unrealized is not None else Decimal(0))
    roi_pct: Decimal | None = None
    if margin is not None and margin > 0 and roi_basis is not None:
        roi_pct = (roi_basis / margin) * Decimal(100)

    if position_match is not None and position_match.is_open:
        lifecycle = "open"
        lifecycle_label = "Nyitott pozíció"
    elif position_match is not None and not position_match.is_open:
        lifecycle = "closed"
        lifecycle_label = "Lezárva"
    elif sym_u in open_symbols:
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

    exchange: dict[str, Any] = {
        "synced": sync_error is None,
        "sync_error": sync_error,
        "order_status": exchange_status,
        "lifecycle": lifecycle,
        "lifecycle_label": lifecycle_label,
        "realized_pnl_usdt": str(realized) if realized is not None else None,
        "unrealized_pnl_usdt": (
            str(unrealized) if unrealized is not None else None
        ),
        "roi_pct": (
            str(roi_pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            if roi_pct is not None
            else None
        ),
        "margin_usdt_estimate": (
            str(margin.quantize(Decimal("0.0001"))) if margin is not None else None
        ),
        "position_id": position_match.position_id if position_match else None,
    }

    if include_debug:
        roi_blocked: str | None = None
        if margin is None or margin <= 0:
            roi_blocked = "no_margin (qty×price/leverage nem számolható)"
        elif realized is None:
            roi_blocked = "no_realized (nincs PnL forrás)"
        dbg: dict[str, Any] = {
            "history_row_found": hist_row is not None,
            "history_row_keys": sorted(hist_row.keys())[:50] if hist_row else [],
            "history_clientId_raw": hist_row.get("clientId") if hist_row else None,
            "history_orderId_raw": hist_row.get("orderId") if hist_row else None,
            "history_positionId_raw": (hist_row.get("positionId") if hist_row else None)
            or (hist_row.get("position_id") if hist_row else None),
            "history_status_raw": exchange_status,
            "history_realized_raw": hist_row.get("realizedPNL") if hist_row else None,
            "realized_hist_parsed": str(realized_hist)
            if realized_hist is not None
            else None,
            "realized_effective": str(realized) if realized is not None else None,
            "trade_augment_chosen": {
                "realized_sum": str(trade_augment.realized_sum),
                "avg_price": str(trade_augment.avg_price),
            }
            if trade_augment
            else None,
            "position_match": {
                "position_id": position_match.position_id,
                "is_open": position_match.is_open,
                "side": position_match.side,
                "realized_pnl": str(position_match.realized_pnl),
                "unrealized_pnl": str(position_match.unrealized_pnl),
                "margin": str(position_match.margin)
                if position_match.margin is not None
                else None,
                "entry_price": str(position_match.entry_price)
                if position_match.entry_price is not None
                else None,
                "close_price": str(position_match.close_price)
                if position_match.close_price is not None
                else None,
                "qty": str(position_match.qty)
                if position_match.qty is not None
                else None,
                "leverage": position_match.leverage,
            }
            if position_match
            else None,
            "qty_for_margin": str(qty),
            "leverage_used": lev,
            "price_hist": str(price_hist) if price_hist else None,
            "price_db": str(db_price) if db_price else None,
            "price_trade_vwap": str(ta_price) if ta_price else None,
            "price_ticker_fallback": str(mp) if mp else None,
            "price_chosen_for_margin": str(price) if price and price > 0 else None,
            "margin_usdt": str(margin) if margin else None,
            "roi_blocked": roi_blocked,
            "symbol_in_open_positions": sym_u in open_symbols,
        }
        if debug_extras:
            dbg["extras"] = debug_extras
        exchange["debug"] = dbg

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
        "exchange": exchange,
        "entry_context": o.entry_context,
    }
