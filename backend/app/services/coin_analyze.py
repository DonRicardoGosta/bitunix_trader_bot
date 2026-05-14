"""Egy szimbólum kline-alapú swing / „simított” szakasz elemzése.

5 gyertyás Bill Williams-fraktál swing pontok, összevonás azonos oldalú
szomszédokra (csúcs/csúcs → magasabb csúcs), majd szomszédos swingok közötti
**láb** choppiness szűréssel: a láb „egyenesebb”, ha a záró árak összes
abszolút lépése nem sokkal nagyobb a nettó elmozdulásnál (alacsony choppiness).

A medián a tiszta lábak ``move_pct`` értékeire vonatkozik (nettó százalék a
láb elejétől végéig, záró árakkal).

Opcionális **walk-forward** blokk: az időintervallum közepénél kettévágva az első
félen számolt tiszta-láb medián fele szimmetrikus TP/SL, a hátsó fél gyertyáin
előbb-utóbb melyik szint érintődött (egyszerű irány-heurisztika + konzervatív
azon-gyertya döntés).
"""

from __future__ import annotations

import math
from decimal import Decimal
from itertools import pairwise
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
    # Adjacent swing pairs: ``pairwise`` (not ``zip(..., strict=True)``, which
    # requires equal-length iterables and would always fail for n vs n-1).
    for a, b in pairwise(swings):
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


def split_klines_time_midpoint(
    klines: list[dict[str, Decimal]],
    *,
    min_train: int = 15,
    min_test: int = 5,
) -> tuple[list[dict[str, Decimal]], list[dict[str, Decimal]], int] | None:
    """Időintervallum közepénél kettévágja a sorozatot (első / második fele).

    A ``min_train`` / ``min_test`` a legkisebb gyertya darabszám a walk-forward
    hátsó teszt részéhez (fraktál + TP/SL szimuláció miatt).

    Returns:
        ``(train, test, split_index)`` ahol ``test = klines[split_index:]`` és
        ``train = klines[:split_index]``. ``None``, ha nem osztható értelmesen.
    """
    n = len(klines)
    if n < min_train + min_test:
        return None
    t0 = klines[0]["time"]
    t1 = klines[-1]["time"]
    span = t1 - t0
    if span <= 0:
        return None
    mid_t = t0 + span / Decimal(2)
    split_at = n
    for i, row in enumerate(klines):
        if row["time"] >= mid_t:
            split_at = i
            break
    split_at = max(min_train, min(split_at, n - min_test))
    if split_at < min_train or n - split_at < min_test:
        return None
    return klines[:split_at], klines[split_at:], split_at


def predict_side_from_train_clean_legs(
    train_klines: list[dict[str, Decimal]],
    clean_legs: list[dict[str, Any]],
) -> tuple[Literal["long", "short"], str]:
    """Egyszerű irány-heurisztika az első fél tiszta lábain + nettó záró változás.

    Returns:
        ``(predicted_side, reason_code)``.
    """
    up = sum(1 for leg in clean_legs if leg.get("direction") == "up")
    down = len(clean_legs) - up
    c0 = train_klines[0]["close"]
    c1 = train_klines[-1]["close"]
    net = c1 - c0
    if up > down:
        return "long", "clean_legs_up_majority"
    if down > up:
        return "short", "clean_legs_down_majority"
    if net > 0:
        return "long", "clean_legs_tie_positive_net_close"
    if net < 0:
        return "short", "clean_legs_tie_negative_net_close"
    return "long", "clean_legs_tie_flat_close"


def _simulate_symmetric_tp_sl(
    test_bars: list[dict[str, Decimal]],
    *,
    entry: Decimal,
    move_pct: Decimal,
    side: Literal["long", "short"],
) -> tuple[Literal["tp", "sl", "none"], int | None, bool]:
    """Melyik szint érintődik előbb a teszt gyertyákon (ugyanakkora TP és SL %%).

    Ha egy gyertyán belül mindkettő érinthető, **konzervatív**: SL számít
    előbb ütöttnek (realisztikusabb rossz kitöltés a backtestben).

    Args:
        test_bars: A checkpoint utáni gyertyák (idő szerint növekvő).
        entry: Belépési referenciaár (train utolsó záró).
        move_pct: TP és SL távolsága százalékban (pl. medián/2).
        side: ``long`` vagy ``short``.

    Returns:
        ``(first_touch, bar_offset_in_test, same_bar_ambiguous)``.
    """
    if move_pct <= 0 or entry <= 0 or not test_bars:
        return "none", None, False
    m = move_pct / Decimal(100)
    if side == "long":
        tp_price = entry * (Decimal(1) + m)
        sl_price = entry * (Decimal(1) - m)
        for i, k in enumerate(test_bars):
            hi, lo = k["high"], k["low"]
            tp_hit = hi >= tp_price
            sl_hit = lo <= sl_price
            if tp_hit and sl_hit:
                return "sl", i, True
            if sl_hit:
                return "sl", i, False
            if tp_hit:
                return "tp", i, False
        return "none", None, False
    tp_price = entry * (Decimal(1) - m)
    sl_price = entry * (Decimal(1) + m)
    for i, k in enumerate(test_bars):
        hi, lo = k["high"], k["low"]
        tp_hit = lo <= tp_price
        sl_hit = hi >= sl_price
        if tp_hit and sl_hit:
            return "sl", i, True
        if sl_hit:
            return "sl", i, False
        if tp_hit:
            return "tp", i, False
    return "none", None, False


def build_walk_forward_payload(
    klines: list[dict[str, Decimal]],
    *,
    choppiness_max: Decimal = Decimal("1.72"),
) -> dict[str, Any]:
    """Walk-forward: train = első fél időben, irány + medián/2 TP/SL a teszten.

    A teljes ablak továbbra is külön elemzésre kerül a fő ``clean_legs`` mezőben;
    ez a blokk csak a **félidős** out-of-sample ellenőrzést írja le.
    """
    base: dict[str, Any] = {
        "enabled": False,
        "disabled_reason": None,
        "checkpoint_time_ms": None,
        "train_bar_count": 0,
        "test_bar_count": 0,
        "median_move_pct_train": None,
        "tp_move_pct": None,
        "sl_move_pct": None,
        "entry_price": None,
        "predicted_side": None,
        "prediction_reason": None,
        "test_net_move_pct": None,
        "actual_test_side": None,
        "direction_guess_correct": None,
        "first_touch": None,
        "first_touch_time_ms": None,
        "same_bar_ambiguous": None,
        "strategy_would_win": None,
    }
    split = split_klines_time_midpoint(klines)
    if split is None:
        base["disabled_reason"] = "too_few_candles_or_bad_time_span"
        return base
    train, test, _ = split
    base["train_bar_count"] = len(train)
    base["test_bar_count"] = len(test)
    base["checkpoint_time_ms"] = _to_int_ms(train[-1]["time"])

    train_clean, train_stats = analyze_clean_legs(
        train, choppiness_max=choppiness_max
    )
    med = train_stats.get("median_move_pct")
    if med is None or not isinstance(med, Decimal) or med <= 0:
        base["disabled_reason"] = "no_median_clean_legs_in_train"
        return base

    half_med = med / Decimal(2)
    predicted, reason = predict_side_from_train_clean_legs(train, train_clean)
    entry = train[-1]["close"]

    t0 = test[0]["close"]
    t1 = test[-1]["close"]
    if t0 <= 0:
        base["disabled_reason"] = "invalid_test_prices"
        return base
    test_net = (t1 - t0) / t0 * Decimal(100)
    actual_side: Literal["long", "short"] = "long" if t1 > t0 else "short"
    direction_ok = predicted == actual_side

    touch, bar_off, ambiguous = _simulate_symmetric_tp_sl(
        test,
        entry=entry,
        move_pct=half_med,
        side=predicted,
    )
    ft_ms: int | None = None
    if bar_off is not None and 0 <= bar_off < len(test):
        ft_ms = _to_int_ms(test[bar_off]["time"])

    def _q4(x: Decimal) -> str:
        return str(x.quantize(Decimal("0.0001")))

    base.update(
        {
            "enabled": True,
            "median_move_pct_train": _q4(med),
            "tp_move_pct": _q4(half_med),
            "sl_move_pct": _q4(half_med),
            "entry_price": str(entry),
            "predicted_side": predicted,
            "prediction_reason": reason,
            "test_net_move_pct": _q4(test_net),
            "actual_test_side": actual_side,
            "direction_guess_correct": direction_ok,
            "first_touch": touch,
            "first_touch_time_ms": ft_ms,
            "same_bar_ambiguous": ambiguous,
            "strategy_would_win": touch == "tp",
        }
    )
    return base


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
        "walk_forward": build_walk_forward_payload(
            klines, choppiness_max=choppiness_max
        ),
    }
