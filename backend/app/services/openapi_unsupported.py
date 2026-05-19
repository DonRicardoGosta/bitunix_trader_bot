"""Párok, amelyek a Bitunix OpenAPI-n nem kereskedhetők (pl. code 710002)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.bitunix.exceptions import BitunixAPIError
from app.services.runtime_settings import get_runtime_raw, set_runtime_json_value

RUNTIME_KEY = "bitunix_openapi_unsupported_symbols"
OPENAPI_UNSUPPORTED_PAIR_CODE = "710002"


def is_openapi_trading_unsupported_error(exc: BaseException) -> bool:
    """True ha a Bitunix azt jelzi, hogy a pár nem támogatott OpenAPI kereskedésre."""
    if isinstance(exc, BitunixAPIError) and exc.code == OPENAPI_UNSUPPORTED_PAIR_CODE:
        return True
    msg = str(exc).lower()
    return "does not currently support trading via openapi" in msg


async def load_openapi_unsupported_symbols(session: AsyncSession) -> set[str]:
    raw = await get_runtime_raw(session, RUNTIME_KEY)
    if not raw:
        return set()
    try:
        parsed: Any = json.loads(raw)
    except json.JSONDecodeError:
        return set()
    if not isinstance(parsed, list):
        return set()
    return {str(s).upper() for s in parsed if s}


async def remember_openapi_unsupported_symbol(
    session: AsyncSession, symbol: str
) -> set[str]:
    sym = symbol.upper()
    blocked = await load_openapi_unsupported_symbols(session)
    if sym in blocked:
        return blocked
    blocked.add(sym)
    await set_runtime_json_value(session, RUNTIME_KEY, sorted(blocked))
    return blocked
