"""Bitunix trading_pairs metaadat kinyerése (precision, max leverage)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PairMeta:
    symbol: str
    max_leverage: int
    base_precision: int
    price_precision: int


def extract_bitunix_list(raw: Any) -> list[dict[str, Any]]:
    """A Bitunix válaszok ``data`` mezője hol lista, hol dict – mindkettőt kezeli."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        data = raw.get("data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("list"), list):
            return data["list"]
    return []


def index_trading_pairs(raw: Any) -> dict[str, PairMeta]:
    """``trading_pairs`` válasz → szimbólum → meta map."""
    items = extract_bitunix_list(raw)
    out: dict[str, PairMeta] = {}
    for item in items:
        symbol = item.get("symbol")
        if not symbol:
            continue
        sym = str(symbol).upper()
        max_lev = item.get("maxLeverage") or item.get("max_leverage") or 1
        try:
            max_leverage = int(max_lev)
        except (TypeError, ValueError):
            max_leverage = 1
        precision_raw = (
            item.get("basePrecision")
            or item.get("base_precision")
            or item.get("qtyPrecision")
            or 4
        )
        try:
            base_precision = int(precision_raw)
        except (TypeError, ValueError):
            base_precision = 4
        price_raw = (
            item.get("pricePrecision")
            or item.get("price_precision")
            or item.get("quotePrecision")
            or 4
        )
        try:
            price_precision = int(price_raw)
        except (TypeError, ValueError):
            price_precision = 4
        out[sym] = PairMeta(
            symbol=sym,
            max_leverage=max_leverage,
            base_precision=base_precision,
            price_precision=price_precision,
        )
    return out
