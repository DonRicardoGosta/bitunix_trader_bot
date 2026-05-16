"""Stratégia futtatási réteg: scheduler + egy-shot futtatás."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any

from app.bitunix.client import BitunixClient
from app.bitunix.error_reporting import format_strategy_run_error, structured_exception
from app.bitunix.exceptions import BitunixAPIError, BitunixSignatureError
from app.config import get_settings
from app.db import audit
from app.services.runtime_settings import (
    is_strategy_enabled,
    is_strategy_runner_paused,
    is_trading_paused,
)
from app.services.trading_gate import is_trading_allowed
from app.db.models import AuditLevel, StrategyRun, StrategyRunStatus
from app.db.session import AsyncSessionLocal
from app.services.live_bus import DEFAULT_INVALIDATION_TOPICS, publish_invalidate
from app.services.strategy.base import Strategy, StrategyContext, StrategyResult
from app.services.strategy.registry import (
    STRATEGIES,
    StrategyNotFoundError,
    get_strategy,
)


async def run_strategy(name: str, *, triggered_by: str = "manual") -> dict[str, Any]:
    """Egy stratégia egy lefutása, friss DB sessionben és Bitunix kliensben.

    A ``StrategyRun`` rekord a végén commit-ra kerül, akár hiba van, akár nincs.
    """
    settings = get_settings()
    strategy: Strategy = get_strategy(name)

    async with AsyncSessionLocal() as session:
        if await is_trading_paused(session):
            return {
                "run_id": None,
                "status": "NO_OP",
                "error": None,
                "failure": None,
                "details": {"reason": "trading_paused"},
            }
        if not await is_strategy_enabled(session, settings, name):
            return {
                "run_id": None,
                "status": "NO_OP",
                "error": None,
                "failure": None,
                "details": {"reason": "strategy_disabled"},
            }
        if not await is_trading_allowed(session, settings):
            return {
                "run_id": None,
                "status": "NO_OP",
                "error": None,
                "failure": None,
                "details": {"reason": "trading_gate_closed"},
            }

    async with AsyncSessionLocal() as session:
        run = StrategyRun(
            strategy_name=name,
            status=StrategyRunStatus.RUNNING,
            triggered_by=triggered_by,
        )
        session.add(run)
        await session.flush()
        run_id = run.id
        await session.commit()

    client = BitunixClient(
        api_key=settings.bitunix_api_key,
        api_secret=settings.bitunix_api_secret,
        base_url=settings.bitunix_rest_base_url,
        live_trading=settings.bitunix_live_trading,
    )

    error: str | None = None
    failure_detail: dict[str, Any] | None = None
    result: StrategyResult | None = None
    try:
        async with AsyncSessionLocal() as session:
            ctx = StrategyContext(
                session=session,
                client=client,
                settings=settings,
                triggered_by=triggered_by,
            )
            try:
                result = await strategy.run(ctx)
                await session.commit()
            except (BitunixAPIError, BitunixSignatureError) as exc:
                await session.rollback()
                failure_detail = structured_exception(exc)
                error = format_strategy_run_error(exc)
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                failure_detail = structured_exception(exc)
                error = format_strategy_run_error(exc)
    finally:
        await client.close()

    async with AsyncSessionLocal() as session:
        db_run = await session.get(StrategyRun, run_id)
        if db_run is not None:
            db_run.finished_at = datetime.now(UTC)
            if error:
                db_run.status = StrategyRunStatus.FAILED
                db_run.error = error
                db_run.details = (
                    {"failure": failure_detail} if failure_detail is not None else None
                )
            elif result is None:
                db_run.status = StrategyRunStatus.FAILED
                db_run.error = "no result"
            elif result.is_no_op:
                db_run.status = StrategyRunStatus.NO_OP
                db_run.details = _result_to_details(result)
            else:
                db_run.status = StrategyRunStatus.SUCCESS
                db_run.details = _result_to_details(result)

            audit_msg = (
                f"{name} stratégia futás {db_run.status.value if db_run.status else 'UNKNOWN'} "
                f"(triggered_by={triggered_by})."
            )
            if error and db_run.status == StrategyRunStatus.FAILED:
                short = error if len(error) <= 600 else error[:597] + "…"
                audit_msg += f" Hiba: {short}"

            await audit.record(
                session,
                f"strategy.run.{(db_run.status.value if db_run.status else 'unknown').lower()}",
                level=AuditLevel.ERROR
                if db_run.status == StrategyRunStatus.FAILED
                else AuditLevel.INFO,
                message=audit_msg,
                payload={
                    "run_id": db_run.id,
                    "status": db_run.status.value if db_run.status else None,
                    "error": db_run.error,
                    "failure": failure_detail,
                    "details": db_run.details,
                },
                strategy_name=name,
            )
            await session.commit()

        await publish_invalidate(DEFAULT_INVALIDATION_TOPICS)
        return {
            "run_id": run_id,
            "status": db_run.status.value if db_run and db_run.status else "UNKNOWN",
            "error": error,
            "failure": failure_detail,
            "details": _result_to_details(result) if result else None,
        }


def _result_to_details(result: StrategyResult) -> dict[str, Any]:
    return {
        "placed_orders": result.placed_orders,
        "skipped": result.skipped,
        **result.details,
    }


class StrategyRunner:
    """Egyszerű asyncio-alapú ütemező: minden regisztrált stratégiát rendszeresen futtat.

    Indítás:  ``await runner.start()``
    Leállítás:``await runner.stop()``
    """

    def __init__(self, *, interval_seconds: int = 300) -> None:
        self._interval = max(10, int(interval_seconds))
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="strategy-runner")
        await audit.record_isolated(
            "strategy.runner.started",
            message=f"Scheduler elindítva ({self._interval}s).",
            payload={"interval_seconds": self._interval},
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=self._interval + 5)
            except TimeoutError:
                self._task.cancel()
        await audit.record_isolated(
            "strategy.runner.stopped",
            message="Scheduler leállítva.",
        )

    async def _loop(self) -> None:
        try:
            while not self._stop.is_set():
                settings = get_settings()
                async with AsyncSessionLocal() as session:
                    if await is_strategy_runner_paused(session, settings):
                        with contextlib.suppress(TimeoutError):
                            await asyncio.wait_for(
                                self._stop.wait(), timeout=self._interval
                            )
                        continue
                for name in list(STRATEGIES.keys()):
                    try:
                        await run_strategy(name, triggered_by="scheduler")
                    except StrategyNotFoundError:
                        continue
                    except Exception as exc:  # noqa: BLE001
                        await audit.record_isolated(
                            "strategy.runner.iteration_error",
                            level=AuditLevel.ERROR,
                            message=f"{name}: {exc}",
                            strategy_name=name,
                        )
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
        except asyncio.CancelledError:
            return
