"""Időzített pozíció-zárás hold-window optimalizálás alapján.

Ha a belépő rendelés ``entry_context``-jében szerepel
``hold_window_optimization_enabled`` és ``hold_window_minutes``, a monitor
a belépés után ennyi perccel piaci CLOSE rendelést ad (ha a pozíció még nyitva van).
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.bitunix.exceptions import BitunixAPIError, BitunixSignatureError
from app.config import get_settings
from app.db import audit
from app.db.models import AuditLevel, Order, OrderSide, OrderStatus
from app.db.session import AsyncSessionLocal
from app.schemas.trading import OrderRequest
from app.services.bitunix_client_factory import create_bitunix_client
from app.services.entry_order_prep import (
    OpenEntryPreparationError,
    resolve_open_position_for_exit,
)
from app.services.runtime_settings import is_trading_paused
from app.services.strategy_runtime_config import get_top_signal_entries_config
from app.services.trading import TradingService

_HOLD_EXIT_MAX_FAILURES = 3
_INSUFFICIENT_AMOUNT_CODE = "20008"


def _parse_hold_minutes(ctx: dict | None) -> int | None:
    if not ctx or not ctx.get("hold_window_optimization_enabled"):
        return None
    raw = ctx.get("hold_window_minutes")
    if raw is None:
        hw = ctx.get("hold_window")
        if isinstance(hw, dict):
            raw = hw.get("minutes")
    if raw is None:
        return None
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return None


def _hold_exit_fail_count(ctx: dict | None) -> int:
    if not isinstance(ctx, dict):
        return 0
    try:
        return max(0, int(ctx.get("hold_time_exit_fail_count") or 0))
    except (TypeError, ValueError):
        return 0


async def _orders_due_for_hold_exit(session: AsyncSession) -> list[Order]:
    """Nyitó rendelések, amelyeknél lejárt a hold ablak és még nincs time exit."""
    stmt = (
        sa.select(Order)
        .where(
            Order.strategy_name == "top_signal_entries",
            Order.reduce_only.is_(False),
            Order.status.in_([OrderStatus.NEW, OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED]),
        )
        .order_by(Order.created_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    now = datetime.now(UTC)
    due: list[Order] = []
    for o in rows:
        ctx = o.entry_context
        if not isinstance(ctx, dict) or ctx.get("hold_time_exit_done"):
            continue
        minutes = _parse_hold_minutes(ctx)
        if minutes is None:
            continue
        created = o.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        if now >= created + timedelta(minutes=minutes):
            due.append(o)
    return due


async def run_hold_window_exit_pass() -> int:
    """Egy monitor kör: lejárt hold ablakú pozíciók zárása. Vissza: zárások száma."""
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        if await is_trading_paused(session):
            return 0
        tse = await get_top_signal_entries_config(session)
        if not tse.hold_window_optimization_enabled:
            return 0
        due_orders = await _orders_due_for_hold_exit(session)

    if not due_orders:
        return 0

    closed = 0
    async with AsyncSessionLocal() as session:
        client = await create_bitunix_client(session, settings=settings)
        trading = TradingService(client, session)
        try:
            for order in due_orders:
                db_order = await session.get(Order, order.id)
                if db_order is None:
                    continue
                closed += await _try_hold_window_exit(
                    session,
                    trading,
                    client,
                    db_order,
                )
            await session.commit()
        finally:
            await client.close()
    return closed


async def _try_hold_window_exit(
    session: AsyncSession,
    trading: TradingService,
    client,
    order: Order,
) -> int:
    """Egy belépő rendelés hold-window zárása. Vissza: 1 ha sikerült, egyébként 0."""
    sym = order.symbol.upper()
    side_u = order.side.value.upper()
    try:
        position_id, close_qty = await resolve_open_position_for_exit(
            client,
            symbol=sym,
            side=side_u,
            max_attempts=3,
            delay_seconds=0.2,
        )
    except OpenEntryPreparationError as exc:
        await _mark_hold_exit_done(
            session,
            order,
            reason="position_not_on_exchange",
        )
        await audit.record(
            session,
            "hold_window.exit.skipped_no_position",
            level=AuditLevel.INFO,
            message=f"{sym} {side_u}: nincs nyitott pozíció a tőzsdén ({exc})",
            payload={"client_order_id": order.client_order_id},
            strategy_name="top_signal_entries",
        )
        return 0

    close_req = OrderRequest.model_validate(
        {
            "symbol": sym,
            "side": side_u,
            "tradeSide": "CLOSE",
            "positionId": position_id,
            "orderType": "MARKET",
            "quantity": close_qty,
            "leverage": order.leverage,
            "reduceOnly": True,
        }
    )
    try:
        await trading.place_order(
            close_req,
            strategy_name="top_signal_entries",
            entry_context={
                "hold_time_exit": True,
                "hold_window_minutes": _parse_hold_minutes(order.entry_context),
                "source_open_client_order_id": order.client_order_id,
            },
        )
    except (BitunixAPIError, BitunixSignatureError) as exc:
        return await _handle_hold_exit_place_failed(
            session,
            order,
            sym=sym,
            exc=exc,
        )

    await _mark_hold_exit_done(session, order, reason="time_exit_placed")
    return 1


async def _handle_hold_exit_place_failed(
    session: AsyncSession,
    order: Order,
    *,
    sym: str,
    exc: BitunixAPIError | BitunixSignatureError,
) -> int:
    fail_count = _hold_exit_fail_count(order.entry_context) + 1
    ctx = dict(order.entry_context or {})
    ctx["hold_time_exit_fail_count"] = fail_count
    order.entry_context = ctx
    session.add(order)

    code = getattr(exc, "code", None)
    if code == _INSUFFICIENT_AMOUNT_CODE and fail_count >= _HOLD_EXIT_MAX_FAILURES:
        await _mark_hold_exit_done(
            session,
            order,
            reason="exit_failed_insufficient_amount",
        )
        await audit.record(
            session,
            "hold_window.exit.skipped_insufficient",
            level=AuditLevel.WARNING,
            message=(
                f"{sym} hold exit: elégtelen mennyiség "
                f"({fail_count} próbálkozás után feladva): {exc}"
            ),
            payload={
                "client_order_id": order.client_order_id,
                "fail_count": fail_count,
            },
            strategy_name="top_signal_entries",
        )
        return 0

    if fail_count == 1 or fail_count >= _HOLD_EXIT_MAX_FAILURES:
        await audit.record(
            session,
            "hold_window.exit.place_failed",
            level=AuditLevel.WARNING,
            message=f"{sym} hold exit: {exc}",
            payload={
                "client_order_id": order.client_order_id,
                "fail_count": fail_count,
            },
            strategy_name="top_signal_entries",
        )
    return 0


async def _mark_hold_exit_done(
    session: AsyncSession, order: Order, *, reason: str
) -> None:
    ctx = dict(order.entry_context or {})
    ctx["hold_time_exit_done"] = True
    ctx["hold_time_exit_reason"] = reason
    order.entry_context = ctx
    session.add(order)


class PositionHoldMonitor:
    """Háttér task periodikus hold-window zárásokhoz."""

    def __init__(self, *, interval_seconds: float = 30.0) -> None:
        self._interval = max(5.0, interval_seconds)
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="position-hold-monitor")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await run_hold_window_exit_pass()
            except Exception as exc:  # noqa: BLE001
                async with AsyncSessionLocal() as session:
                    await audit.record(
                        session,
                        "hold_window.monitor_error",
                        level=AuditLevel.ERROR,
                        message=str(exc),
                        strategy_name="top_signal_entries",
                    )
                    await session.commit()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
                return
            except TimeoutError:
                pass
