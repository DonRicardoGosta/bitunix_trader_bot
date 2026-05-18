"""Trading service – köztes réteg a Bitunix kliens és az API között.

Itt történik az audit naplózás (DB), a saját ``client_order_id`` generálás,
és a Bitunix válaszának mapping-elése a saját sémánkra.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bitunix.client import BitunixClient
from app.bitunix.exceptions import BitunixAPIError, BitunixSignatureError
from app.config import get_settings
from app.db import audit
from app.db.models import AuditLevel, Order, OrderSide, OrderStatus, OrderType
from app.schemas.trading import OrderRequest, OrderResponse
from app.services.entry_order_prep import (
    OpenEntryPreparationError,
    attach_full_position_tp_sl,
    prepare_open_entry_order,
)
from app.services.live_bus import DEFAULT_INVALIDATION_TOPICS, publish_invalidate
from app.services.order_enrichment import (
    PositionMatch,
    TradeAugment,
    aggregate_trades_response,
    best_trade_augment,
    build_order_api_dict,
    build_trade_augment_indices,
    earliest_history_start_ms,
    extract_history_position_rows,
    extract_open_position_rows,
    fetch_history_position_rows_for_symbol,
    history_position_pages_for_lookback,
    index_history_orders_by_client_id,
    last_or_mark_price_from_ticker,
    match_position_for_order,
    normalize_str_id,
    parse_open_symbols_from_positions,
    pick_trade_augment,
    position_id_from_row,
    symbols_needing_bulk_history_positions,
)

ORDERS_ENRICHMENT_MAX = 500
ENRICHMENT_CACHE_TTL_SEC = 45.0
MAX_DIRECT_HIST_ORDER_LOOKUPS = 50
MAX_DIRECT_TRADE_BY_ORDER_LOOKUPS = 50

_enrichment_cache: dict[str, tuple[float, EnrichmentSyncState]] = {}


@dataclass
class EnrichmentSyncState:
    """Bitunix szinkron eredménye — cache-elhető, soronkénti build külön."""

    open_syms: set[str]
    open_pos_rows: list[dict[str, Any]]
    history_pos_rows: list[dict[str, Any]]
    hist_by_client: dict[str, dict[str, Any]]
    trade_by_client: dict[str, TradeAugment]
    trade_by_order: dict[str, TradeAugment]
    trade_by_position: dict[tuple[str, str], TradeAugment]
    mark_by_symbol: dict[str, Decimal]
    global_sync_error: str | None
    sync_index_meta: dict[str, Any]


def clear_orders_enrichment_cache() -> None:
    """Új rendelés után / tesztek előtt — közös enrichment cache ürítése."""
    _enrichment_cache.clear()


def _enrichment_cache_key(orders: list[Order], lookback_hours: int | None) -> str:
    syms = ",".join(sorted({o.symbol.upper() for o in orders if o.symbol}))
    newest = ""
    if orders:
        times = [o.created_at for o in orders if o.created_at is not None]
        if times:
            newest = max(times).isoformat()
    return f"lb={lookback_hours}:n={len(orders)}:s={syms}:t={newest}"


def _get_cached_enrichment(key: str) -> EnrichmentSyncState | None:
    entry = _enrichment_cache.get(key)
    if entry is None:
        return None
    ts, state = entry
    if time.monotonic() - ts > ENRICHMENT_CACHE_TTL_SEC:
        _enrichment_cache.pop(key, None)
        return None
    return state


def _set_cached_enrichment(key: str, state: EnrichmentSyncState) -> None:
    _enrichment_cache[key] = (time.monotonic(), state)


def _filter_rows_by_lifecycle(
    rows: list[dict[str, Any]], lifecycle: str | None
) -> list[dict[str, Any]]:
    if not lifecycle:
        return rows
    return [
        r
        for r in rows
        if (r.get("exchange") or {}).get("lifecycle") == lifecycle
    ]


def _new_client_order_id() -> str:
    return f"bt-{uuid.uuid4().hex[:24]}"


class TradingService:
    """Trading műveletek aggregálva."""

    def __init__(self, client: BitunixClient, session: AsyncSession) -> None:
        self._client = client
        self._session = session

    async def place_order(
        self,
        payload: OrderRequest,
        *,
        strategy_name: str | None = None,
        entry_context: dict[str, Any] | None = None,
    ) -> OrderResponse:
        """Rendelés feladása + DB audit log + audit_event.

        Args:
            payload: Megrendelés sémája.
            strategy_name: Ha stratégia indította, annak neve.
            entry_context: Stratégia-belépés összefoglaló (WF win rate, forrás stb.).
        """
        client_order_id = payload.client_order_id or _new_client_order_id()
        settings = get_settings()

        if payload.trade_side == "OPEN" and not payload.reduce_only:
            payload = await prepare_open_entry_order(
                client=self._client,
                session=self._session,
                payload=payload,
                settings=settings,
            )

        order = Order(
            client_order_id=client_order_id,
            symbol=payload.symbol,
            side=OrderSide(payload.side),
            type=OrderType(payload.order_type),
            quantity=payload.quantity,
            price=payload.price,
            leverage=payload.leverage,
            status=OrderStatus.NEW,
            reduce_only=payload.reduce_only,
            strategy_name=strategy_name,
            entry_context=entry_context,
        )
        use_position_tpsl = (
            payload.trade_side == "OPEN"
            and not payload.reduce_only
            and payload.tp_price is not None
            and payload.sl_price is not None
        )
        tp_stop = payload.tp_stop_type
        sl_stop = payload.sl_stop_type
        tpsl_error: str | None = None

        async with self._session.begin_nested():
            self._session.add(order)
            await self._session.flush()
            response = await self._client.place_order(
                symbol=payload.symbol,
                side=payload.side,
                order_type=payload.order_type,
                quantity=payload.quantity,
                price=payload.price,
                reduce_only=payload.reduce_only,
                client_order_id=client_order_id,
                trade_side=payload.trade_side,
                position_id=payload.position_id,
                tp_price=None if use_position_tpsl else payload.tp_price,
                sl_price=None if use_position_tpsl else payload.sl_price,
                tp_stop_type=tp_stop,
                sl_stop_type=sl_stop,
            )

            dry_run = bool(response.get("dryRun"))
            if use_position_tpsl:
                try:
                    tpsl_resp = await attach_full_position_tp_sl(
                        self._client,
                        symbol=payload.symbol,
                        side=payload.side,
                        tp_price=payload.tp_price,  # type: ignore[arg-type]
                        sl_price=payload.sl_price,  # type: ignore[arg-type]
                        tp_stop_type=tp_stop,
                        sl_stop_type=sl_stop,
                        dry_run_entry=dry_run,
                        client_order_id=client_order_id,
                        place_order_response=response,
                    )
                    response = {
                        **response,
                        "positionTpSl": tpsl_resp,
                        "tpsl_mode": "position_full",
                    }
                except OpenEntryPreparationError as exc:
                    tpsl_error = str(exc)
                    response = {
                        **response,
                        "tpsl_mode": "position_full",
                        "positionTpSl": None,
                        "tpsl_attach_error": tpsl_error,
                    }
            order.raw_response = json.dumps(response, default=str)
            if not dry_run:
                data = response.get("data") or {}
                bitunix_id = data.get("orderId") or response.get("orderId")
                if bitunix_id:
                    order.bitunix_order_id = str(bitunix_id)

        audit_level = AuditLevel.INFO
        audit_msg = (
            f"{payload.side} {payload.symbol} qty={payload.quantity} "
            f"lev={payload.leverage}x (dry_run={dry_run})"
        )
        if tpsl_error:
            audit_level = AuditLevel.WARNING
            audit_msg = (
                f"{payload.symbol} {payload.side}: belépés OK, TP/SL rögzítés sikertelen: "
                f"{tpsl_error}"
            )
        await audit.record(
            self._session,
            "trade.order_placed" if not tpsl_error else "trade.tpsl_attach_failed",
            level=audit_level,
            message=audit_msg,
            payload={
                "client_order_id": client_order_id,
                "bitunix_order_id": order.bitunix_order_id,
                "symbol": payload.symbol,
                "side": payload.side,
                "order_type": payload.order_type,
                "quantity": str(payload.quantity),
                "price": str(payload.price) if payload.price else None,
                "leverage": payload.leverage,
                "reduce_only": payload.reduce_only,
                "trade_side": payload.trade_side,
                "position_id": payload.position_id,
                "tp_price": str(payload.tp_price) if payload.tp_price else None,
                "sl_price": str(payload.sl_price) if payload.sl_price else None,
                "dry_run": dry_run,
                "entry_context": entry_context,
                "tpsl_attach_error": tpsl_error,
            },
            strategy_name=strategy_name,
        )
        await self._session.commit()
        clear_orders_enrichment_cache()
        await publish_invalidate(DEFAULT_INVALIDATION_TOPICS)

        return OrderResponse(
            client_order_id=client_order_id,
            bitunix_order_id=order.bitunix_order_id,
            status=order.status.value,
            dry_run=dry_run,
            raw=response,
        )

    async def list_orders(
        self,
        limit: int = 50,
        *,
        offset: int = 0,
        symbol: str | None = None,
        lookback_hours: int | None = None,
        lifecycle: str | None = None,
        debug_sync: bool = False,
    ) -> list[dict[str, Any]]:
        """Legutóbbi rendelések DB-ből, Bitunix history + nyitott pozíció szinkronnal.

        Args:
            limit: Maximális visszaadott sorok száma.
            offset: Kihagyott sorok száma (paginálás).
            symbol: Opcionális szimbólum szűrő (case-insensitive).
            lookback_hours: Ha megadva: csak ennyi óra visszamenő ``created_at``.
            lifecycle: Pl. ``closed`` – csak az adott életciklusú sorok.
            debug_sync: Ha true, hibakereső metaadat is jön.
        """
        stmt = select(Order).order_by(Order.created_at.desc())
        if lookback_hours is not None:
            since = datetime.now(UTC) - timedelta(hours=max(1, lookback_hours))
            stmt = stmt.where(Order.created_at >= since)
        if symbol:
            stmt = stmt.where(Order.symbol == symbol.upper())
        stmt = stmt.offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        orders = list(result.scalars().all())
        rows = await self._enriched_order_api_rows(
            orders, debug_sync=debug_sync, lookback_hours=lookback_hours
        )
        filtered = _filter_rows_by_lifecycle(rows, lifecycle)
        if lifecycle:
            return filtered[offset : offset + limit] if offset else filtered[:limit]
        return filtered

    async def orders_pnl_totals(
        self, *, lookback_hours: int | None = None, lifecycle: str | None = None
    ) -> dict[str, Any]:
        """Összesített PnL (USDT) a saját ``orders`` tábla soraira.

        Ugyanaz a Bitunix szinkron és enrichment, mint a rendeléslistánál;
        az összeg a soronkénti ``realized_pnl_usdt`` + ``unrealized_pnl_usdt``
        összege (ahol a mező ki van töltve).
        """
        stmt = select(Order).order_by(Order.created_at.desc())
        if lookback_hours is not None:
            since = datetime.now(UTC) - timedelta(hours=max(1, lookback_hours))
            stmt = stmt.where(Order.created_at >= since)
        stmt = stmt.limit(ORDERS_ENRICHMENT_MAX)
        result = await self._session.execute(stmt)
        orders = list(result.scalars().all())
        rows = await self._enriched_order_api_rows(
            orders, debug_sync=False, lookback_hours=lookback_hours
        )
        rows = _filter_rows_by_lifecycle(rows, lifecycle)
        total_r = Decimal(0)
        total_u = Decimal(0)
        for row in rows:
            ex = row.get("exchange") or {}
            raw_r = ex.get("realized_pnl_usdt")
            raw_u = ex.get("unrealized_pnl_usdt")
            if raw_r is not None:
                total_r += Decimal(str(raw_r))
            if raw_u is not None:
                total_u += Decimal(str(raw_u))
        sync_error = None
        if rows:
            ex0 = rows[0].get("exchange") or {}
            sync_error = ex0.get("sync_error")
        return {
            "lookback_hours": lookback_hours,
            "lifecycle_filter": lifecycle,
            "order_count": len(rows),
            "realized_pnl_usdt": str(total_r),
            "unrealized_pnl_usdt": str(total_u),
            "total_pnl_usdt": str(total_r + total_u),
            "sync_error": sync_error,
        }

    async def _enriched_order_api_rows(
        self,
        orders: list[Order],
        *,
        debug_sync: bool,
        lookback_hours: int | None = None,
    ) -> list[dict[str, Any]]:
        settings = get_settings()

        if not (settings.bitunix_api_key and settings.bitunix_api_secret):
            return [
                build_order_api_dict(
                    o,
                    hist_row=None,
                    open_symbols=set(),
                    sync_error="Bitunix API kulcs nincs beállítva – nincs tőzsdei szinkron.",
                    include_debug=debug_sync,
                    debug_extras={"reason": "missing_api_credentials"},
                )
                for o in orders
            ]

        if not orders:
            return []

        cache_key = _enrichment_cache_key(orders, lookback_hours)
        sync_state: EnrichmentSyncState | None = None
        if not debug_sync:
            sync_state = _get_cached_enrichment(cache_key)
        if sync_state is None:
            sync_state = await self._build_enrichment_sync_state(
                orders, lookback_hours=lookback_hours
            )
            if not debug_sync:
                _set_cached_enrichment(cache_key, sync_state)

        return [
            self._order_api_row(
                o,
                hist_by_client=sync_state.hist_by_client,
                open_syms=sync_state.open_syms,
                global_sync_error=sync_state.global_sync_error,
                trade_by_client=sync_state.trade_by_client,
                trade_by_order=sync_state.trade_by_order,
                trade_by_position=sync_state.trade_by_position,
                mark_by_symbol=sync_state.mark_by_symbol,
                open_pos_rows=sync_state.open_pos_rows,
                history_pos_rows=sync_state.history_pos_rows,
                include_debug=debug_sync,
                sync_index_meta=sync_state.sync_index_meta,
            )
            for o in orders
        ]

    async def _build_enrichment_sync_state(
        self,
        orders: list[Order],
        *,
        lookback_hours: int | None,
    ) -> EnrichmentSyncState:
        """Bitunix adatok összegyűjtése — positionId első, bulk history csak fallback."""
        open_syms: set[str] = set()
        open_pos_rows: list[dict[str, Any]] = []
        got_any_exchange = False
        sync_err: str | None = None
        end_ms = int(datetime.now(UTC).timestamp() * 1000)

        try:
            pos_raw = await self._client.get_positions()
            open_syms = parse_open_symbols_from_positions(pos_raw)
            open_pos_rows = extract_open_position_rows(pos_raw)
            got_any_exchange = True
        except (BitunixAPIError, BitunixSignatureError) as exc:
            sync_err = f"Pozíciók lekérése: {exc}"[:500]

        hist_by_client: dict[str, dict[str, Any]] = {}
        trade_by_client: dict[str, TradeAugment] = {}
        trade_by_order: dict[str, TradeAugment] = {}
        mark_by_symbol: dict[str, Decimal] = {}
        symbols = {o.symbol for o in orders if o.symbol}

        for sym in sorted(symbols):
            start_ms = earliest_history_start_ms(
                orders, sym, lookback_hours=lookback_hours
            )
            try:
                raw = await self._client.get_history_orders(
                    symbol=sym, limit=100, start_time_ms=start_ms, end_time_ms=end_ms
                )
                hist_by_client.update(index_history_orders_by_client_id(raw))
                got_any_exchange = True
            except (BitunixAPIError, BitunixSignatureError) as exc:
                if sync_err is None:
                    sync_err = f"History ({sym}): {exc}"[:500]
                elif len(sync_err) < 450:
                    sync_err = f"{sync_err}; {sym}: {exc}"[:500]

        for sym in sorted(symbols):
            start_ms = earliest_history_start_ms(
                orders, sym, lookback_hours=lookback_hours
            )
            try:
                raw_t = await self._client.get_history_trades(
                    symbol=sym,
                    limit=100,
                    start_time_ms=start_ms,
                    end_time_ms=end_ms,
                )
                bc, bo = build_trade_augment_indices(raw_t)
                trade_by_client.update(bc)
                trade_by_order.update(bo)
                got_any_exchange = True
            except (BitunixAPIError, BitunixSignatureError) as exc:
                if sync_err is None:
                    sync_err = f"Trades ({sym}): {exc}"[:500]
                elif len(sync_err) < 450:
                    sync_err = f"{sync_err}; trades {sym}: {exc}"[:500]

        seen_hist_pair: set[tuple[str, str]] = set()
        direct_hist_lookups = 0
        for o in orders:
            if direct_hist_lookups >= MAX_DIRECT_HIST_ORDER_LOOKUPS:
                break
            cid_key = normalize_str_id(o.client_order_id) or o.client_order_id
            key = (o.symbol, cid_key)
            if cid_key in hist_by_client or key in seen_hist_pair:
                continue
            seen_hist_pair.add(key)
            direct_hist_lookups += 1
            start_ms = earliest_history_start_ms(
                orders, o.symbol, lookback_hours=lookback_hours
            )
            try:
                raw = await self._client.get_history_orders(
                    symbol=o.symbol,
                    client_id=o.client_order_id,
                    limit=100,
                    start_time_ms=start_ms,
                    end_time_ms=end_ms,
                )
                hist_by_client.update(index_history_orders_by_client_id(raw))
                got_any_exchange = True
            except (BitunixAPIError, BitunixSignatureError) as exc:
                if sync_err is None:
                    sync_err = f"History direct ({o.symbol}): {exc}"[:500]
                elif len(sync_err) < 450:
                    sync_err = f"{sync_err}; hist {o.symbol}: {exc}"[:500]

        history_pos_rows: list[dict[str, Any]] = []
        history_pos_ids: set[tuple[str, str]] = set()
        seen_hist_pos_fetch: set[tuple[str, str]] = set()

        for o in orders:
            if o.reduce_only:
                continue
            cid_key = normalize_str_id(o.client_order_id) or o.client_order_id
            hr = hist_by_client.get(cid_key) or hist_by_client.get(o.client_order_id)
            pid = position_id_from_row(hr) if hr else None
            if not pid:
                continue
            pkey = (o.symbol.upper(), pid)
            if pkey in history_pos_ids or pkey in seen_hist_pos_fetch:
                continue
            seen_hist_pos_fetch.add(pkey)
            start_ms = earliest_history_start_ms(
                orders, o.symbol, lookback_hours=lookback_hours
            )
            try:
                raw_hp = await self._client.get_history_positions(
                    symbol=o.symbol,
                    position_id=pid,
                    limit=100,
                    start_time_ms=start_ms,
                    end_time_ms=end_ms,
                )
                for row in extract_history_position_rows(raw_hp):
                    history_pos_rows.append(row)
                    history_pos_ids.add(pkey)
                got_any_exchange = True
            except (BitunixAPIError, BitunixSignatureError):
                pass

        bulk_symbols = symbols_needing_bulk_history_positions(orders, hist_by_client)
        pages = history_position_pages_for_lookback(lookback_hours)
        for sym in sorted(bulk_symbols):
            start_ms = earliest_history_start_ms(
                orders, sym, lookback_hours=lookback_hours
            )
            try:
                for row in await fetch_history_position_rows_for_symbol(
                    self._client,
                    symbol=sym,
                    start_time_ms=start_ms,
                    end_time_ms=end_ms,
                    pages=pages,
                    lookback_hours=lookback_hours,
                ):
                    pid = position_id_from_row(row)
                    key = (sym.upper(), pid or "")
                    if pid and key in history_pos_ids:
                        continue
                    if pid:
                        history_pos_ids.add(key)
                    history_pos_rows.append(row)
                got_any_exchange = True
            except (BitunixAPIError, BitunixSignatureError) as exc:
                if sync_err is None:
                    sync_err = f"History pozíciók ({sym}): {exc}"[:500]
                elif len(sync_err) < 450:
                    sync_err = f"{sync_err}; hist_pos {sym}: {exc}"[:500]

        seen_trade_oid: set[tuple[str, str]] = set()
        direct_trade_lookups = 0
        for o in orders:
            if direct_trade_lookups >= MAX_DIRECT_TRADE_BY_ORDER_LOOKUPS:
                break
            if not o.bitunix_order_id:
                continue
            oid = str(o.bitunix_order_id)
            key = (o.symbol, oid)
            if key in seen_trade_oid:
                continue
            seen_trade_oid.add(key)
            direct_trade_lookups += 1
            start_ms = earliest_history_start_ms(
                orders, o.symbol, lookback_hours=lookback_hours
            )
            try:
                raw_t = await self._client.get_history_trades(
                    symbol=o.symbol,
                    order_id=oid,
                    limit=100,
                    start_time_ms=start_ms,
                    end_time_ms=end_ms,
                )
                bc, bo = build_trade_augment_indices(raw_t)
                trade_by_client.update(bc)
                trade_by_order.update(bo)
                got_any_exchange = True
            except (BitunixAPIError, BitunixSignatureError) as exc:
                if sync_err is None:
                    sync_err = f"Trades orderId ({o.symbol}): {exc}"[:500]
                elif len(sync_err) < 450:
                    sync_err = f"{sync_err}; trades oid {o.symbol}: {exc}"[:500]

        trade_by_position: dict[tuple[str, str], TradeAugment] = {}
        seen_pos: set[tuple[str, str]] = set()
        for o in orders:
            cid_key = normalize_str_id(o.client_order_id) or o.client_order_id
            hr = hist_by_client.get(cid_key) or hist_by_client.get(o.client_order_id)
            pid = position_id_from_row(hr) if hr else None
            if not pid:
                continue
            pkey = (o.symbol.upper(), pid)
            if pkey in seen_pos:
                continue
            seen_pos.add(pkey)
            start_ms = earliest_history_start_ms(
                orders, o.symbol, lookback_hours=lookback_hours
            )
            try:
                raw_p = await self._client.get_history_trades(
                    symbol=o.symbol,
                    position_id=pid,
                    limit=100,
                    start_time_ms=start_ms,
                    end_time_ms=end_ms,
                )
                trade_by_position[pkey] = aggregate_trades_response(raw_p)
                got_any_exchange = True
            except (BitunixAPIError, BitunixSignatureError):
                pass

        for sym in sorted(symbols):
            try:
                raw_m = await self._client.get_ticker(sym)
                mp = last_or_mark_price_from_ticker(raw_m)
                if mp is not None:
                    mark_by_symbol[sym.upper()] = mp
                got_any_exchange = True
            except (BitunixAPIError, BitunixSignatureError) as exc:
                if sync_err is None:
                    sync_err = f"Ticker ({sym}): {exc}"[:500]
                elif len(sync_err) < 450:
                    sync_err = f"{sync_err}; ticker {sym}: {exc}"[:500]

        if not got_any_exchange and sync_err is None:
            sync_err = "Bitunix szinkron sikertelen."

        global_sync_error = None if got_any_exchange else sync_err
        sync_index_meta = {
            "hist_by_client_count": len(hist_by_client),
            "trade_by_client_count": len(trade_by_client),
            "trade_by_order_count": len(trade_by_order),
            "trade_by_position_count": len(trade_by_position),
            "open_pos_count": len(open_pos_rows),
            "history_pos_count": len(history_pos_rows),
            "hist_client_id_prefix_sample": sorted(hist_by_client.keys())[:20],
            "bulk_history_symbols": sorted(bulk_symbols),
        }

        return EnrichmentSyncState(
            open_syms=open_syms,
            open_pos_rows=open_pos_rows,
            history_pos_rows=history_pos_rows,
            hist_by_client=hist_by_client,
            trade_by_client=trade_by_client,
            trade_by_order=trade_by_order,
            trade_by_position=trade_by_position,
            mark_by_symbol=mark_by_symbol,
            global_sync_error=global_sync_error,
            sync_index_meta=sync_index_meta,
        )

    def _order_api_row(
        self,
        o: Order,
        *,
        hist_by_client: dict[str, dict[str, Any]],
        open_syms: set[str],
        global_sync_error: str | None,
        trade_by_client: dict[str, TradeAugment],
        trade_by_order: dict[str, TradeAugment],
        trade_by_position: dict[tuple[str, str], TradeAugment],
        mark_by_symbol: dict[str, Decimal],
        open_pos_rows: list[dict[str, Any]],
        history_pos_rows: list[dict[str, Any]],
        include_debug: bool = False,
        sync_index_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cid_key = normalize_str_id(o.client_order_id) or o.client_order_id
        hr = hist_by_client.get(cid_key) or hist_by_client.get(o.client_order_id)
        pid = (hr or {}).get("positionId") or (hr or {}).get("position_id")
        aug_pos = trade_by_position.get((o.symbol.upper(), str(pid))) if pid else None
        aug_pick = pick_trade_augment(
            trade_by_client,
            trade_by_order,
            client_order_id=o.client_order_id,
            bitunix_order_id=o.bitunix_order_id,
        )
        aug = best_trade_augment(aug_pos, aug_pick)
        hint_pid = position_id_from_row(hr) if hr else None
        pos_match: PositionMatch | None = match_position_for_order(
            o,
            open_position_rows=open_pos_rows,
            history_position_rows=history_pos_rows,
            hint_position_id=hint_pid,
        )
        extras: dict[str, Any] | None = None
        if include_debug:
            extras = {
                "sync_index_meta": sync_index_meta,
                "aug_position": {
                    "realized_sum": str(aug_pos.realized_sum),
                    "avg_price": str(aug_pos.avg_price),
                }
                if aug_pos
                else None,
                "aug_from_client_or_order": {
                    "realized_sum": str(aug_pick.realized_sum),
                    "avg_price": str(aug_pick.avg_price),
                }
                if aug_pick
                else None,
                "aug_best_chosen": {
                    "realized_sum": str(aug.realized_sum),
                    "avg_price": str(aug.avg_price),
                }
                if aug
                else None,
            }
        return build_order_api_dict(
            o,
            hist_row=hr,
            open_symbols=open_syms,
            sync_error=global_sync_error,
            trade_augment=aug,
            mark_price=mark_by_symbol.get(o.symbol.upper()),
            position_match=pos_match,
            include_debug=include_debug,
            debug_extras=extras,
        )


async def estimate_notional(
    *, quantity: Decimal, price: Decimal, leverage: int
) -> Decimal:
    """Pozíció nominális értéke (egyszerű segédfüggvény teszthez is).

    Megjegyzés: a *margin* számítás már külön modulban: ``app/services/risk.py``.
    """
    if leverage <= 0:
        raise ValueError("leverage must be positive")
    return (quantity * price) / leverage
