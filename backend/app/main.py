"""FastAPI alkalmazás belépési pont.

Megjegyzés a logolásról: a *business* események mind a DB ``audit_events``
táblájába kerülnek (lásd ``app/db/audit.py``). Stdout-ra csak az induló /
leállási banner megy, hogy a konténerek életjelet adjanak.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import (
    account,
    events,
    health,
    market,
    orders,
    positions,
    strategies,
)
from app.config import get_settings
from app.db import audit
from app.db.models import AuditLevel
from app.services.strategy.runner import StrategyRunner


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    print(
        f"[bitunix-trader] startup env={settings.app_env} "
        f"live_trading={settings.bitunix_live_trading} version={__version__}",
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
                "live_trading": settings.bitunix_live_trading,
            },
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[bitunix-trader] audit init failed: {exc}", file=sys.stderr, flush=True)

    runner: StrategyRunner | None = None
    if settings.strategy_runner_enabled:
        runner = StrategyRunner(
            interval_seconds=settings.strategy_interval_seconds,
        )
        await runner.start()
        app.state.strategy_runner = runner

    try:
        yield
    finally:
        if runner is not None:
            await runner.stop()
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.backend_cors_origins,
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

    return app


app = create_app()
