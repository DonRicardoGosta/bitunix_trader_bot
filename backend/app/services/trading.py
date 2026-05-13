"""Trading service – köztes réteg a Bitunix kliens és az API között.

Itt történik az audit naplózás (DB), a saját ``client_order_id`` generálás,
és a Bitunix válaszának mapping-elése a saját sémánkra.
"""

from __future__ import annotations

import json
import uuid
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
from app.services.order_enrichment import (
    TradeAugment,
    aggregate_trades_response,
    best_trade_augment,
    build_order_api_dict,
    build_trade_augment_indices,
    earliest_history_start_ms,
    index_closed_positions,
    index_history_orders_by_client_id,
    last_or_mark_price_from_ticker,
    normalize_str_id,
    parse_open_symbols_from_positions,
    pick_trade_augment,
)


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
    ) -> OrderResponse:
        """Rendelés feladása + DB audit log + audit_event.

        Args:
            payload: Megrendelés sémája.
            strategy_name: Ha stratégia indította, annak neve.
        """
        client_order_id = payload.client_order_id or _new_client_order_id()

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
        )
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
                tp_price=payload.tp_price,
                sl_price=payload.sl_price,
                tp_stop_type=payload.tp_stop_type,
                sl_stop_type=payload.sl_stop_type,
            )

            dry_run = bool(response.get("dryRun"))
            order.raw_response = json.dumps(response, default=str)
            if not dry_run:
                data = response.get("data") or {}
                bitunix_id = data.get("orderId") or response.get("orderId")
                if bitunix_id:
                    order.bitunix_order_id = str(bitunix_id)

        await audit.record(
            self._session,
            "trade.order_placed",
            level=AuditLevel.INFO,
            message=(
                f"{payload.side} {payload.symbol} qty={payload.quantity} "
                f"lev={payload.leverage}x (dry_run={dry_run})"
            ),
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
            },
            strategy_name=strategy_name,
        )
        await self._session.commit()

        return OrderResponse(
            client_order_id=client_order_id,
            bitunix_order_id=order.bitunix_order_id,
            status=order.status.value,
            dry_run=dry_run,
            raw=response,
        )

    async def list_orders(self, limit: int = 50, *, debug_sync: bool = False) -> list[dict[str, Any]]:
        """Legutóbbi rendelések DB-ből, Bitunix history + nyitott pozíció szinkronnal."""
        stmt = select(Order).order_by(Order.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        orders = list(result.scalars().all())
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

        open_syms: set[str] = set()
        got_any_exchange = False
        sync_err: str | None = None
        try:
            pos_raw = await self._client.get_positions()
            open_syms = parse_open_symbols_from_positions(pos_raw)
            got_any_exchange = True
        except (BitunixAPIError, BitunixSignatureError) as exc:
            sync_err = f"Pozíciók lekérése: {exc}"[:500]

        hist_by_client: dict[str, dict[str, Any]] = {}
        trade_by_client: dict[str, TradeAugment] = {}
        trade_by_order: dict[str, TradeAugment] = {}
        mark_by_symbol: dict[str, Decimal] = {}
        symbols = {o.symbol for o in orders if o.symbol}
        for sym in sorted(symbols):
            start_ms = earliest_history_start_ms(orders, sym)
            try:
                raw = await self._client.get_history_orders(
                    symbol=sym, limit=100, start_time_ms=start_ms
                )
                hist_by_client.update(index_history_orders_by_client_id(raw))
                got_any_exchange = True
            except (BitunixAPIError, BitunixSignatureError) as exc:
                if sync_err is None:
                    sync_err = f"History ({sym}): {exc}"[:500]
                elif len(sync_err) < 450:
                    sync_err = f"{sync_err}; {sym}: {exc}"[:500]

        for sym in sorted(symbols):
            start_ms = earliest_history_start_ms(orders, sym)
            try:
                raw_t = await self._client.get_history_trades(
                    symbol=sym, limit=100, start_time_ms=start_ms
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

        # Célzott lekérések: a top-100-as lista gyakran nem tartalmazza a saját clientId-t.
        seen_hist_pair: set[tuple[str, str]] = set()
        for o in orders:
            cid_key = normalize_str_id(o.client_order_id) or o.client_order_id
            key = (o.symbol, cid_key)
            if cid_key in hist_by_client or key in seen_hist_pair:
                continue
            seen_hist_pair.add(key)
            start_ms = earliest_history_start_ms(orders, o.symbol)
            try:
                raw = await self._client.get_history_orders(
                    symbol=o.symbol,
                    client_id=o.client_order_id,
                    limit=100,
                    start_time_ms=start_ms,
                )
                hist_by_client.update(index_history_orders_by_client_id(raw))
                got_any_exchange = True
            except (BitunixAPIError, BitunixSignatureError) as exc:
                if sync_err is None:
                    sync_err = f"History direct ({o.symbol}): {exc}"[:500]
                elif len(sync_err) < 450:
                    sync_err = f"{sync_err}; hist {o.symbol}: {exc}"[:500]

        seen_trade_oid: set[tuple[str, str]] = set()
        for o in orders:
            if not o.bitunix_order_id:
                continue
            oid = str(o.bitunix_order_id)
            key = (o.symbol, oid)
            if key in seen_trade_oid:
                continue
            seen_trade_oid.add(key)
            start_ms = earliest_history_start_ms(orders, o.symbol)
            try:
                raw_t = await self._client.get_history_trades(
                    symbol=o.symbol, order_id=oid, limit=100, start_time_ms=start_ms
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
            if not hr:
                continue
            pid = hr.get("positionId") or hr.get("position_id")
            if not pid:
                continue
            pkey = (o.symbol.upper(), str(pid))
            if pkey in seen_pos:
                continue
            seen_pos.add(pkey)
            start_ms = earliest_history_start_ms(orders, o.symbol)
            try:
                raw_p = await self._client.get_history_trades(
                    symbol=o.symbol,
                    position_id=str(pid),
                    limit=100,
                    start_time_ms=start_ms,
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

        closed_by_sym_pid: dict[tuple[str, str], dict[str, Any]] = {}
        for sym in sorted(symbols):
            start_ms = earliest_history_start_ms(orders, sym)
            try:
                rph = await self._client.get_history_positions(
                    symbol=sym, limit=100, start_time_ms=start_ms
                )
                closed_by_sym_pid.update(index_closed_positions(rph))
                got_any_exchange = True
            except (BitunixAPIError, BitunixSignatureError) as exc:
                if sync_err is None:
                    sync_err = f"Lezárt pozíciók ({sym}): {exc}"[:500]
                elif len(sync_err) < 450:
                    sync_err = f"{sync_err}; hist_pos {sym}: {exc}"[:500]

        for o in orders:
            cid_key2 = normalize_str_id(o.client_order_id) or o.client_order_id
            hr2 = hist_by_client.get(cid_key2) or hist_by_client.get(o.client_order_id)
            if not hr2:
                continue
            pid2 = hr2.get("positionId") or hr2.get("position_id")
            if not pid2:
                continue
            pkey2 = (o.symbol.upper(), str(pid2))
            if pkey2 in closed_by_sym_pid:
                continue
            start_ms = earliest_history_start_ms(orders, o.symbol)
            try:
                rph = await self._client.get_history_positions(
                    symbol=o.symbol,
                    position_id=str(pid2),
                    limit=100,
                    start_time_ms=start_ms,
                )
                closed_by_sym_pid.update(index_closed_positions(rph))
                got_any_exchange = True
            except (BitunixAPIError, BitunixSignatureError) as exc:
                if sync_err is None:
                    sync_err = f"Lezárt pozíció (pid={pid2}): {exc}"[:500]
                elif len(sync_err) < 450:
                    sync_err = f"{sync_err}; hist_pos pid: {exc}"[:500]

        if not got_any_exchange and sync_err is None:
            sync_err = "Bitunix szinkron sikertelen."

        global_sync_error = None if got_any_exchange else sync_err

        sync_index_meta = {
            "hist_by_client_count": len(hist_by_client),
            "trade_by_client_count": len(trade_by_client),
            "trade_by_order_count": len(trade_by_order),
            "trade_by_position_count": len(trade_by_position),
            "closed_positions_indexed": len(closed_by_sym_pid),
            "hist_client_id_prefix_sample": sorted(hist_by_client.keys())[:20],
        }

        return [
            self._order_api_row(
                o,
                hist_by_client=hist_by_client,
                open_syms=open_syms,
                global_sync_error=global_sync_error,
                trade_by_client=trade_by_client,
                trade_by_order=trade_by_order,
                trade_by_position=trade_by_position,
                closed_by_sym_pid=closed_by_sym_pid,
                mark_by_symbol=mark_by_symbol,
                include_debug=debug_sync,
                sync_index_meta=sync_index_meta,
            )
            for o in orders
        ]

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
        closed_by_sym_pid: dict[tuple[str, str], dict[str, Any]],
        mark_by_symbol: dict[str, Decimal],
        include_debug: bool = False,
        sync_index_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cid_key = normalize_str_id(o.client_order_id) or o.client_order_id
        hr = hist_by_client.get(cid_key) or hist_by_client.get(o.client_order_id)
        pid = (hr or {}).get("positionId") or (hr or {}).get("position_id")
        closed_row = (
            closed_by_sym_pid.get((o.symbol.upper(), str(pid))) if pid else None
        )
        aug_pos = (
            trade_by_position.get((o.symbol.upper(), str(pid)))
            if pid
            else None
        )
        aug_pick = pick_trade_augment(
            trade_by_client,
            trade_by_order,
            client_order_id=o.client_order_id,
            bitunix_order_id=o.bitunix_order_id,
        )
        aug = best_trade_augment(aug_pos, aug_pick)
        extras: dict[str, Any] | None = None
        if include_debug:
            extras = {
                "sync_index_meta": sync_index_meta,
                "closed_position_row": {
                    "realizedPNL": closed_row.get("realizedPNL"),
                    "entryPrice": closed_row.get("entryPrice"),
                    "positionId": closed_row.get("positionId"),
                }
                if closed_row
                else None,
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
            closed_position_row=closed_row,
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
