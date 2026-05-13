"""Trading service – köztes réteg a Bitunix kliens és az API között.

Itt történik az audit naplózás (DB), a saját ``client_order_id`` generálás,
és a Bitunix válaszának mapping-elése a saját sémánkra.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bitunix.client import BitunixClient
from app.db import audit
from app.db.models import AuditLevel, Order, OrderSide, OrderStatus, OrderType
from app.schemas.trading import OrderRequest, OrderResponse


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
        self._session.add(order)
        await self._session.flush()

        response = await self._client.place_order(
            symbol=payload.symbol,
            side=payload.side,
            order_type=payload.order_type,
            quantity=payload.quantity,
            price=payload.price,
            leverage=payload.leverage,
            reduce_only=payload.reduce_only,
            client_order_id=client_order_id,
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

    async def list_orders(self, limit: int = 50) -> list[Order]:
        """Legutóbbi rendelések a saját DB-ből."""
        stmt = select(Order).order_by(Order.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


async def estimate_notional(
    *, quantity: Decimal, price: Decimal, leverage: int
) -> Decimal:
    """Pozíció nominális értéke (egyszerű segédfüggvény teszthez is).

    Megjegyzés: a *margin* számítás már külön modulban: ``app/services/risk.py``.
    """
    if leverage <= 0:
        raise ValueError("leverage must be positive")
    return (quantity * price) / leverage
