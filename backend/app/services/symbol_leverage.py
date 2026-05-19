"""Szimbólumonkénti max tőkeáttétel (trading_pairs + change_leverage)."""

from __future__ import annotations

from app.bitunix.client import BitunixClient
from app.services.risk import effective_order_leverage
from app.services.trading_pairs_meta import PairMeta


class SymbolLeverageError(ValueError):
    """Nem állapítható meg vagy nem állítható a párhoz tartozó leverage."""


def resolve_leverage_for_symbol(
    symbol: str,
    pair_meta: dict[str, PairMeta],
) -> tuple[int, int]:
    """``(effektív_leverage, tőzsdei_max)`` — ugyanaz, mint live belépésnél."""
    sym = symbol.upper()
    meta = pair_meta.get(sym)
    if meta is None:
        raise SymbolLeverageError(f"{sym} nincs a trading_pairs listában")
    pair_max = max(1, int(meta.max_leverage))
    return effective_order_leverage(pair_max), pair_max


async def ensure_symbol_max_leverage(
    client: BitunixClient,
    *,
    symbol: str,
    pair_meta: dict[str, PairMeta],
    margin_coin: str,
) -> tuple[int, int]:
    """Max. engedélyezett leverage a számlán (live trade előtt / kalibráció scan)."""
    eff, pair_max = resolve_leverage_for_symbol(symbol, pair_meta)
    await client.change_leverage(
        symbol=symbol.upper(),
        leverage=eff,
        margin_coin=margin_coin,
    )
    return eff, pair_max
