"""FastAPI alkalmazás belépési pont.

Megjegyzés a logolásról: a *business* események mind a DB ``audit_events``
táblájába kerülnek (lásd ``app/db/audit.py``). Stdout-ra csak az induló /
leállási banner megy, hogy a konténerek életjelet adjanak.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import (
    account,
    analytics,
    calibration,
    dashboard,
    events,
    health,
    live,
    market,
    orders,
    positions,
    settings as settings_routes,
    strategies,
)
from app.config import get_settings
from app.db import audit
from app.db.models import AuditLevel
from app.services.calibration_runner import CalibrationRunner
from app.services.live_bus import LIVE_UI_TICK_TOPICS, publish_invalidate
from app.services.live_bus import subscriber_count as live_subscriber_count
from app.services.strategy.runner import StrategyRunner


async def _live_ui_push_tick(stop: asyncio.Event) -> None:
    """Rendszeres invalidáció, ha van websocket kliens (REST frissítést vált ki)."""
    while not stop.is_set():
        settings = get_settings()
        interval = max(0.3, float(settings.live_ui_push_interval_seconds))
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            return
        except TimeoutError:
            pass
        if live_subscriber_count() == 0:
            continue
        await publish_invalidate(LIVE_UI_TICK_TOPICS)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    print(
        f"[bitunix-trader] startup env={settings.app_env} "
        f"live_trading=runtime(db) version={__version__}",
        file=sys.stdout,
        flush=True,
    )
    try:
        await audit.record_isolated(
            "app.startup",
            level=AuditLevel.INFO,
            message="Backend elindult.",
            payload={
                "version": __version__,
                "env": settings.app_env,
            },
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[bitunix-trader] audit init failed: {exc}", file=sys.stderr, flush=True)

    calibration_runner: CalibrationRunner | None = None
    if settings.calibration_enabled:
        calibration_runner = CalibrationRunner(
            interval_seconds=settings.calibration_interval_seconds,
        )
        await calibration_runner.start()
        app.state.calibration_runner = calibration_runner

    runner: StrategyRunner | None = None
    if settings.strategy_runner_enabled:
        runner = StrategyRunner(
            interval_seconds=settings.strategy_interval_seconds,
        )
        await runner.start()
        app.state.strategy_runner = runner

    live_push_stop = asyncio.Event()
    live_push_task: asyncio.Task[None] | None = None
    if settings.live_ui_push_enabled and settings.live_ui_push_interval_seconds > 0:
        live_push_task = asyncio.create_task(
            _live_ui_push_tick(live_push_stop),
            name="live-ui-push-tick",
        )
    app.state.live_push_task = live_push_task

    try:
        yield
    finally:
        live_push_stop.set()
        if live_push_task is not None:
            live_push_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await live_push_task
        if runner is not None:
            await runner.stop()
        if calibration_runner is not None:
            await calibration_runner.stop()
        print("[bitunix-trader] shutdown", file=sys.stdout, flush=True)
        with contextlib.suppress(Exception):
            await audit.record_isolated(
                "app.shutdown",
                level=AuditLevel.INFO,
                message="Backend leállt.",
            )


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Bitunix Trader API",
        version=__version__,
        description=(
            "Bitunix Futures kereskedő alkalmazás backendje. "
            "Lásd: https://openapidoc.bitunix.com/"
        ),
        lifespan=lifespan,
    )

    _cors = [o.strip() for o in settings.backend_cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(market.router, prefix="/api")
    app.include_router(orders.router, prefix="/api")
    app.include_router(positions.router, prefix="/api")
    app.include_router(account.router, prefix="/api")
    app.include_router(strategies.router, prefix="/api")
    app.include_router(events.router, prefix="/api")
    app.include_router(calibration.router, prefix="/api")
    app.include_router(dashboard.router, prefix="/api")
    app.include_router(analytics.router, prefix="/api")
    app.include_router(settings_routes.router, prefix="/api")
    app.include_router(live.router, prefix="/api")

    return app


app = create_app()
