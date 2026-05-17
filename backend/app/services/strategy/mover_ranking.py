"""Közös 24h ticker rangsorolás és segédfüggvények a stratégiákhoz."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.services.trading_pairs_meta import extract_bitunix_list as _extract_list


class Mover:
    """Egy futures szimbólum 24h ticker összefoglalója."""

    __slots__ = ("symbol", "last_price", "change_pct", "high", "low")

    def __init__(
        self,
        symbol: str,
        last_price: Decimal,
        change_pct: Decimal,
        high: Decimal | None,
        low: Decimal | None,
    ) -> None:
        self.symbol = symbol
        self.last_price = last_price
        self.change_pct = change_pct
        self.high = high
        self.low = low

    @property
    def range_position(self) -> Decimal | None:
        """Az aktuális ár pozíciója a 24h tartományban (0=low, 1=high)."""
        if self.high is None or self.low is None or self.high <= self.low:
            return None
        return (self.last_price - self.low) / (self.high - self.low)


def decide_direction(
    mover: Mover,
    *,
    mode: str,
    range_threshold: Decimal,
) -> tuple[str | None, str]:
    """Pozíció irányának eldöntése a beállított logikával.

    Args:
        mover: Egy top mover ticker.
        mode: ``"trend"`` | ``"momentum_breakout"`` | ``"mean_revert"``.
        range_threshold: A momentum_breakout szűrőhöz (alap: 0.66) –
            a felső ``threshold`` és alsó ``1-threshold`` zónába kell esnie.

    Returns:
        ``(side, reason)`` – ahol side ``"BUY"`` / ``"SELL"`` vagy ``None``
        (skip). A ``reason`` rövid magyarázat a döntésről.
    """
    change_positive = mover.change_pct > 0
    change_negative = mover.change_pct < 0
    pos = mover.range_position

    if mode == "trend":
        if change_positive:
            return "BUY", "trend: 24h változás pozitív"
        if change_negative:
            return "SELL", "trend: 24h változás negatív"
        return None, "trend: 0 változás"

    if mode == "mean_revert":
        if change_positive:
            return "SELL", "mean_revert: pozitív mover -> short (fade)"
        if change_negative:
            return "BUY", "mean_revert: negatív mover -> long (fade)"
        return None, "mean_revert: 0 változás"

    # default: momentum_breakout
    if pos is None:
        return None, "no_range_data"
    lower = Decimal(1) - range_threshold
    if change_positive and pos >= range_threshold:
        return "BUY", f"breakout: pos={pos:.2f} >= {range_threshold}"
    if change_negative and pos <= lower:
        return "SELL", f"breakdown: pos={pos:.2f} <= {lower}"
    return None, f"momentum_mixed: change>0={change_positive}, pos={pos:.2f}"


def to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def parse_open_position_symbols(raw: Any) -> set[str]:
    """Bitunix ``get_pending_positions`` / hasonló válaszból: nem nulla méretű pozíciók."""
    out: set[str] = set()
    for row in _extract_list(raw):
        sym = row.get("symbol") or row.get("symbolName")
        if not sym:
            continue
        for key in (
            "positionAmt",
            "qty",
            "positionQty",
            "holdVol",
            "size",
            "volume",
            "positionSize",
        ):
            val = row.get(key)
            if val is None:
                continue
            try:
                amt = Decimal(str(val))
            except Exception:
                continue
            if amt != 0:
                out.add(str(sym).upper())
                break
    return out


def rank_top_movers(raw: Any, *, top_n: int) -> list[Mover]:
    """Bitunix ticker válaszból top-N mover lista (abszolút % csökkenő)."""
    items = _extract_list(raw)
    movers: list[Mover] = []
    for item in items:
        symbol = item.get("symbol")
        last = to_decimal(item.get("lastPrice") or item.get("last"))
        open_p = to_decimal(item.get("open"))
        if not symbol or last is None or open_p is None or open_p == 0:
            continue
        change_pct = ((last - open_p) / open_p) * Decimal(100)
        high = to_decimal(item.get("high") or item.get("high24h"))
        low = to_decimal(item.get("low") or item.get("low24h"))
        movers.append(
            Mover(
                symbol=symbol,
                last_price=last,
                change_pct=change_pct,
                high=high,
                low=low,
            )
        )
    movers.sort(key=lambda m: abs(m.change_pct), reverse=True)
    return movers[:top_n]


def extract_available_usdt(raw: Any) -> Decimal:
    """Az ``available`` USDT egyenleg kibontása a ``/futures/account`` válaszból."""
    if isinstance(raw, dict):
        data = raw.get("data", raw)
        if isinstance(data, list) and data:
            data = data[0]
        if isinstance(data, dict):
            for key in ("available", "availableBalance", "balance"):
                val = to_decimal(data.get(key))
                if val is not None:
                    return val
    return Decimal(0)
