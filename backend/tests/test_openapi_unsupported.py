"""OpenAPI-n nem kereskedhető párok felismerése és cache."""

from __future__ import annotations

import pytest

from app.bitunix.exceptions import BitunixAPIError
from app.services.openapi_unsupported import (
    OPENAPI_UNSUPPORTED_PAIR_CODE,
    is_openapi_trading_unsupported_error,
    load_openapi_unsupported_symbols,
    remember_openapi_unsupported_symbol,
)


def test_is_openapi_trading_unsupported_error_by_code() -> None:
    exc = BitunixAPIError(
        "pair blocked",
        code=OPENAPI_UNSUPPORTED_PAIR_CODE,
    )
    assert is_openapi_trading_unsupported_error(exc)


def test_is_openapi_trading_unsupported_error_by_message() -> None:
    exc = BitunixAPIError(
        "This trading pair does not currently support trading via OpenAPI."
    )
    assert is_openapi_trading_unsupported_error(exc)


@pytest.mark.asyncio
async def test_remember_openapi_unsupported_symbol_persists() -> None:
    import sqlalchemy as sa

    from app.db.base import Base
    from app.db.models import AppRuntimeSetting
    from app.db.session import AsyncSessionLocal, engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        await session.execute(
            sa.delete(AppRuntimeSetting).where(
                AppRuntimeSetting.key == "bitunix_openapi_unsupported_symbols"
            )
        )
        await session.commit()

    async with AsyncSessionLocal() as session:
        blocked = await remember_openapi_unsupported_symbol(session, "amznusdt")
        await session.commit()
        assert blocked == {"AMZNUSDT"}

    async with AsyncSessionLocal() as session:
        loaded = await load_openapi_unsupported_symbols(session)
        assert loaded == {"AMZNUSDT"}
