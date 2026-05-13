"""FastAPI alkalmazás belépési pont."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import account, health, market, orders, positions
from app.config import get_settings
from app.logging_setup import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        json_output=settings.is_production,
    )
    log = structlog.get_logger(__name__)
    log.info(
        "app.startup",
        env=settings.app_env,
        live_trading=settings.bitunix_live_trading,
        version=__version__,
    )
    yield
    log.info("app.shutdown")


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

    return app


app = create_app()
