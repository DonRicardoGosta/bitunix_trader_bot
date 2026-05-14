"""Egy szimbólum kline-alapú swing / „simított” szakasz elemzése.

5 gyertyás Bill Williams-fraktál swing pontok, összevonás azonos oldalú
szomszédokra (csúcs/csúcs → magasabb csúcs), majd szomszédos swingok közötti
**láb** choppiness szűréssel: a láb „egyenesebb”, ha a záró árak összes
abszolút lépése nem sokkal nagyobb a nettó elmozdulásnál (alacsony choppiness).

A medián a tiszta lábak ``move_pct`` értékeire vonatkozik (nettó százalék a
láb elejétől végéig, záró árakkal).
"""

from __future__ import annotations

import math
from decimal import Decimal
from statistics import median
from typing import Any, Literal

from app.services.calibration import parse_klines

# Bitunix ``get_klines`` intervallumok (perc / gyertya).
_INTERVAL_BAR_MINUTES: list[tuple[str, int]] = [
    ("1m", 1),
    ("5m", 5),
    ("15m", 15),
    ("30m", 30),
    ("1h", 60),
    ("2h", 120),
    ("4h", 240),
    ("6h", 360),
    ("8h", 480),
    ("12h", 720),
    ("1d", 1440),
    ("3d", 4320),
    ("1w", 10080),
]


def plan_kline_interval(lookback_minutes: int) -> tuple[str, int]:
    """Válassz legfinomabb intervallumot, hogy ``limit`` ≤ 200 legyen.

    Args:
        lookback_minutes: Felhasználói lookback legalább pár perc.

    Returns:
        ``(interval, limit)`` a Bitunix ``get_klines`` híváshoz.
    """
    lb = max(5, int(lookback_minutes))
    for interval, bar_m in _INTERVAL_BAR_MINUTES:
        need = int(math.ceil(lb / bar_m))
        if 2 <= need <= 200:
            return interval, need
    return ("1w", 200)


def _to_int_ms(t: Decimal) -> int:
    """Bitunix idő: másodperc vagy millis – egységesen ms."""
    v = int(t)
    if v < 10**11:
        return v * 1000
    return v


def fractal_swings(
    klines: list[dict[str, Decimal]],
) -> list[tuple[int, Literal["H", "L"], Decimal]]:
    """5 gyertyás fraktál swing pontok (index, típus, swing ár)."""
    n = len(klines)
    if n < 5:
        return []
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    out: list[tuple[int, Literal["H", "L"], Decimal]] = []
    for i in range(2, n - 2):
        win_h = highs[i - 2 : i + 3]
        win_l = lows[i - 2 : i + 3]
        is_h = (
            highs[i] == max(win_h)
            and highs[i] > highs[i - 1]
            and highs[i] > highs[i + 1]
        )
        is_l = (
            lows[i] == min(win_l)
            and lows[i] < lows[i - 1]
            and lows[i] < lows[i + 1]
        )
        if is_h and is_l:
            is_l = False
        if is_h:
            out.append((i, "H", highs[i]))
        elif is_l:
            out.append((i, "L", lows[i]))
    out.sort(key=lambda x: x[0])
    return out


def merge_same_side_swings(
    swings: list[tuple[int, Literal["H", "L"], Decimal]],
) -> list[tuple[int, Literal["H", "L"], Decimal]]:
    """Szomszédos azonos típusú swingek összevonása (erősebb extrémum marad)."""
    merged: list[tuple[int, Literal["H", "L"], Decimal]] = []
    for idx, kind, price in swings:
        if not merged:
            merged.append((idx, kind, price))
            continue
        _, pk, pp = merged[-1]
        if pk != kind:
            merged.append((idx, kind, price))
            continue
        if kind == "H" and price > pp or kind == "L" and price < pp:
            merged[-1] = (idx, kind, price)
    return merged


def leg_choppiness(
    closes: list[Decimal],
    start_i: int,
    end_i: int,
) -> Decimal:
    """Összes záró lépés / |nettó záró elmozdulás| (≥ 1)."""
    if end_i <= start_i:
        return Decimal(1)
    path = sum(
        abs(closes[i] - closes[i - 1])
        for i in range(start_i + 1, end_i + 1)
    )
    disp = abs(closes[end_i] - closes[start_i])
    tiny = Decimal("1e-12")
    return path / max(disp, tiny)


def analyze_clean_legs(
    klines: list[dict[str, Decimal]],
    *,
    choppiness_max: Decimal = Decimal("1.72"),
    min_move_pct: Decimal = Decimal("0.04"),
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Swing lábak choppiness + minimális mozgás szerinti szűrése.

    Returns:
        ``(clean_leg_dicts, stats)`` – stats tartalmazza a mediánt, darabszámot.
    """
    if len(klines) < 5:
        return [], {
            "median_move_pct": None,
            "mean_move_pct": None,
            "clean_leg_count": 0,
            "all_leg_count": 0,
        }

    closes = [k["close"] for k in klines]
    times = [k["time"] for k in klines]
    raw_swings = fractal_swings(klines)
    swings = merge_same_side_swings(raw_swings)
    if len(swings) < 2:
        return [], {
            "median_move_pct": None,
            "mean_move_pct": None,
            "clean_leg_count": 0,
            "all_leg_count": 0,
        }

    clean: list[dict[str, Any]] = []
    for a, b in zip(swings, swings[1:], strict=True):
        i0, _, p0 = a
        i1, _, p1 = b
        if i1 <= i0:
            continue
        chop = leg_choppiness(closes, i0, i1)
        if p0 <= 0:
            continue
        move_pct = abs(p1 - p0) / p0 * Decimal(100)
        if chop > choppiness_max or move_pct < min_move_pct:
            continue
        direction: Literal["up", "down"] = "up" if p1 > p0 else "down"
        clean.append(
            {
                "start_index": i0,
                "end_index": i1,
                "start_time_ms": _to_int_ms(times[i0]),
                "end_time_ms": _to_int_ms(times[i1]),
                "direction": direction,
                "move_pct": move_pct,
                "choppiness": chop,
                "start_price": p0,
                "end_price": p1,
            }
        )

    moves = [leg["move_pct"] for leg in clean]
    stats: dict[str, Any] = {
        "median_move_pct": (median(moves) if moves else None),
        "mean_move_pct": (
            sum(moves, Decimal(0)) / Decimal(len(moves)) if moves else None
        ),
        "clean_leg_count": len(clean),
        "all_leg_count": max(0, len(swings) - 1),
    }
    return clean, stats


def build_coin_analysis_payload(
    *,
    symbol: str,
    max_leverage: int,
    lookback_minutes: int,
    interval: str,
    kline_limit: int,
    klines_raw: dict[str, Any],
    choppiness_max: Decimal = Decimal("1.72"),
) -> dict[str, Any]:
    """Teljes API válasz dict összeállítása (Pydantic model_validate-hoz)."""
    klines = parse_klines(klines_raw)
    clean, stats = analyze_clean_legs(klines, choppiness_max=choppiness_max)
    candles: list[dict[str, Any]] = []
    for k in klines:
        candles.append(
            {
                "time_ms": _to_int_ms(k["time"]),
                "open": str(k["open"]),
                "high": str(k["high"]),
                "low": str(k["low"]),
                "close": str(k["close"]),
            }
        )
    legs_out: list[dict[str, Any]] = []
    for leg in clean:
        legs_out.append(
            {
                "start_time_ms": leg["start_time_ms"],
                "end_time_ms": leg["end_time_ms"],
                "start_index": leg["start_index"],
                "end_index": leg["end_index"],
                "direction": leg["direction"],
                "move_pct": str(leg["move_pct"].quantize(Decimal("0.0001"))),
                "choppiness": str(leg["choppiness"].quantize(Decimal("0.0001"))),
                "start_price": str(leg["start_price"]),
                "end_price": str(leg["end_price"]),
            }
        )
    med = stats["median_move_pct"]
    mean = stats["mean_move_pct"]

    def _fmt_move_stat(x: object | None) -> str | None:
        if x is None:
            return None
        d = x if isinstance(x, Decimal) else Decimal(str(x))
        return str(d.quantize(Decimal("0.0001")))

    return {
        "symbol": symbol,
        "max_leverage": max_leverage,
        "interval": interval,
        "kline_limit": kline_limit,
        "lookback_minutes_requested": lookback_minutes,
        "choppiness_max": str(choppiness_max),
        "candles": candles,
        "clean_legs": legs_out,
        "median_move_pct": _fmt_move_stat(med),
        "mean_move_pct": _fmt_move_stat(mean),
        "clean_leg_count": stats["clean_leg_count"],
        "all_leg_count": stats["all_leg_count"],
    }
