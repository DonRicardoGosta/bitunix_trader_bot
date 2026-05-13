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
    build_order_api_dict,
    build_trade_augment_indices,
    index_history_orders_by_client_id,
    last_or_mark_price_from_ticker,
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

    async def list_orders(self, limit: int = 50) -> list[dict[str, Any]]:
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
            try:
                raw = await self._client.get_history_orders(symbol=sym, limit=100)
                hist_by_client.update(index_history_orders_by_client_id(raw))
                got_any_exchange = True
            except (BitunixAPIError, BitunixSignatureError) as exc:
                if sync_err is None:
                    sync_err = f"History ({sym}): {exc}"[:500]
                elif len(sync_err) < 450:
                    sync_err = f"{sync_err}; {sym}: {exc}"[:500]

        for sym in sorted(symbols):
            try:
                raw_t = await self._client.get_history_trades(symbol=sym, limit=100)
                bc, bo = build_trade_augment_indices(raw_t)
                trade_by_client.update(bc)
                trade_by_order.update(bo)
                got_any_exchange = True
            except (BitunixAPIError, BitunixSignatureError) as exc:
                if sync_err is None:
                    sync_err = f"Trades ({sym}): {exc}"[:500]
                elif len(sync_err) < 450:
                    sync_err = f"{sync_err}; trades {sym}: {exc}"[:500]

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

        return [
            build_order_api_dict(
                o,
                hist_row=hist_by_client.get(o.client_order_id),
                open_symbols=open_syms,
                sync_error=global_sync_error,
                trade_augment=pick_trade_augment(
                    trade_by_client,
                    trade_by_order,
                    client_order_id=o.client_order_id,
                    bitunix_order_id=o.bitunix_order_id,
                ),
                mark_price=mark_by_symbol.get(o.symbol.upper()),
            )
            for o in orders
        ]


async def estimate_notional(
    *, quantity: Decimal, price: Decimal, leverage: int
) -> Decimal:
    """Pozíció nominális értéke (egyszerű segédfüggvény teszthez is).

    Megjegyzés: a *margin* számítás már külön modulban: ``app/services/risk.py``.
    """
    if leverage <= 0:
        raise ValueError("leverage must be positive")
    return (quantity * price) / leverage
