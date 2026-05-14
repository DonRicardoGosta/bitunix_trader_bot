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
        is_l = lows[i] == min(win_l) and lows[i] < lows[i - 1] and lows[i] < lows[i + 1]
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
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(start_i + 1, end_i + 1))
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


def split_klines_at_time_fraction(
    klines: list[dict[str, Decimal]],
    fraction: Decimal,
    *,
    min_train: int = 15,
    min_test: int = 5,
) -> tuple[list[dict[str, Decimal]], list[dict[str, Decimal]], int] | None:
    """Időtengely mentén ``fraction`` aránynál vág (train előtte, teszt utána).

    ``fraction`` ∈ (0, 1): a teljes időintervallum ``t0 + span * fraction``
    pillanatában kezdődik a teszt (első gyertya, amelyik időben eléri vagy
    meghaladja ezt a határt).

    Returns:
        ``(train, test, split_index)`` ahol ``test = klines[split_index:]``.
        ``None``, ha nem osztható értelmesen.
    """
    n = len(klines)
    if n < min_train + min_test:
        return None
    t0 = klines[0]["time"]
    t1 = klines[-1]["time"]
    span = t1 - t0
    if span <= 0:
        return None
    frac = max(Decimal("0.01"), min(fraction, Decimal("0.99")))
    mid_t = t0 + span * frac
    split_at = n
    for i, row in enumerate(klines):
        if row["time"] >= mid_t:
            split_at = i
            break
    split_at = max(min_train, min(split_at, n - min_test))
    if split_at < min_train or n - split_at < min_test:
        return None
    return klines[:split_at], klines[split_at:], split_at


def split_klines_time_midpoint(
    klines: list[dict[str, Decimal]],
    *,
    min_train: int = 15,
    min_test: int = 5,
) -> tuple[list[dict[str, Decimal]], list[dict[str, Decimal]], int] | None:
    """Időintervallum közepénél kettévágja (``fraction = 0.5``)."""
    return split_klines_at_time_fraction(
        klines, Decimal("0.5"), min_train=min_train, min_test=min_test
    )


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


def _simulate_tp_sl(
    test_bars: list[dict[str, Decimal]],
    *,
    entry: Decimal,
    tp_move_pct: Decimal,
    sl_move_pct: Decimal,
    side: Literal["long", "short"],
) -> tuple[Literal["tp", "sl", "none"], int | None, bool]:
    """Melyik szint érintődik előbb (külön TP és SL ármozgás %%).

    Ha egy gyertyán belül mindkettő érinthető, **konzervatív**: SL számít előbb ütöttnek.

    Args:
        test_bars: A belépés utáni gyertyák (idő szerint növekvő).
        entry: Belépési referenciaár (train utolsó záró).
        tp_move_pct: TP távolság százalékban (pl. ``medián * k_tp``).
        sl_move_pct: SL távolság százalékban (pl. ``medián * k_sl``).
        side: ``long`` vagy ``short``.

    Returns:
        ``(first_touch, bar_offset_in_test, same_bar_ambiguous)``.
    """
    if tp_move_pct <= 0 or sl_move_pct <= 0 or entry <= 0 or not test_bars:
        return "none", None, False
    m_tp = tp_move_pct / Decimal(100)
    m_sl = sl_move_pct / Decimal(100)
    if side == "long":
        tp_price = entry * (Decimal(1) + m_tp)
        sl_price = entry * (Decimal(1) - m_sl)
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
    tp_price = entry * (Decimal(1) - m_tp)
    sl_price = entry * (Decimal(1) + m_sl)
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


def _simulate_symmetric_tp_sl(
    test_bars: list[dict[str, Decimal]],
    *,
    entry: Decimal,
    move_pct: Decimal,
    side: Literal["long", "short"],
) -> tuple[Literal["tp", "sl", "none"], int | None, bool]:
    """Ugyanakkora TP és SL %% — visszafelé kompatibilis API."""
    return _simulate_tp_sl(
        test_bars,
        entry=entry,
        tp_move_pct=move_pct,
        sl_move_pct=move_pct,
        side=side,
    )


def _next_bar_index_after_cooldown(
    klines: list[dict[str, Decimal]],
    exit_bar_index: int,
    cooldown_minutes: int,
) -> int | None:
    """Az ``exit_bar`` időpontja + cooldown utáni első gyertya indexe."""
    if cooldown_minutes <= 0:
        nxt = exit_bar_index + 1
        return nxt if nxt < len(klines) else None
    if exit_bar_index < 0 or exit_bar_index >= len(klines):
        return None
    exit_ms = _to_int_ms(klines[exit_bar_index]["time"])
    need_ms = exit_ms + cooldown_minutes * 60 * 1000
    for j in range(exit_bar_index + 1, len(klines)):
        if _to_int_ms(klines[j]["time"]) >= need_ms:
            return j
    return None


def _tp_sl_prices_for_side(
    entry: Decimal,
    tp_move_pct: Decimal,
    sl_move_pct: Decimal,
    side: Literal["long", "short"],
) -> tuple[Decimal, Decimal]:
    """TP és SL célárak külön %% mozgással (mindkettő pozitív százalék)."""
    if side == "long":
        tp = entry * (Decimal(1) + tp_move_pct / Decimal(100))
        sl = entry * (Decimal(1) - sl_move_pct / Decimal(100))
    else:
        tp = entry * (Decimal(1) - tp_move_pct / Decimal(100))
        sl = entry * (Decimal(1) + sl_move_pct / Decimal(100))
    return tp, sl


# Variációs szekvencia: effektív ár %-mozgás belépéstől TP/SL szintig (nem leverage ROI).
_WF_VAR_TP_MOVE_PCT_MIN = Decimal("30")
_WF_VAR_TP_MOVE_PCT_MAX = Decimal("300")
_WF_VAR_SL_MOVE_PCT_MIN = Decimal("10")
_WF_VAR_SL_MOVE_PCT_MAX = Decimal("150")


def _clip_variation_tpsl_move_pct(
    tp_move_pct: Decimal,
    sl_move_pct: Decimal,
) -> tuple[Decimal, Decimal]:
    """Variációs szimuláció: csak **felső** korlát (TP ≤300%%, SL ≤150%%).

    A TP ≥30%% / SL ≥10%% követelmény **nem** felfelé klipel — különben minden kis
    medián×szorzó ugyanarra a 30/10-re esne, és a rács sorai megegyeznének.
    """
    return (
        min(_WF_VAR_TP_MOVE_PCT_MAX, tp_move_pct),
        min(_WF_VAR_SL_MOVE_PCT_MAX, sl_move_pct),
    )


def _coerce_sl_move_pct_le_tp(
    tp_move_pct: Decimal,
    sl_move_pct: Decimal,
) -> tuple[Decimal, Decimal]:
    """SL %% távolság nem lehet nagyobb a TP %% távolságnál (medián×szorzó + vágások után)."""
    return (tp_move_pct, min(sl_move_pct, tp_move_pct))


def _variation_meets_min_tpsl_pct_profile(
    tp_move_pct_raw: Decimal,
    sl_move_pct_raw: Decimal,
) -> bool:
    """Ajánlási profil: első belépéshez tartozó nyers %% legalább a minimum sávban."""
    return (
        tp_move_pct_raw >= _WF_VAR_TP_MOVE_PCT_MIN
        and sl_move_pct_raw >= _WF_VAR_SL_MOVE_PCT_MIN
    )


_WF_MIN_TRADES_LAST_24H_FOR_RECOMMENDATION = 5

# Szekvenciális WF: egy trade ne fogyassza el az összes hátralévő gyertyát (TP/SL nélkül),
# különben nincs hely következő belépésre cooldown után.
_WF_SEQ_MIN_FORWARD_CHUNK_BARS = 16


def _trade_forward_window_bars(
    remaining_bars: int,
    *,
    max_trade_forward_bars: int | None = None,
) -> int:
    """Hány gyertyán át szimulálunk egy trade-re (TP/SL vagy horizont vég)."""
    if remaining_bars <= 0:
        return 0
    if max_trade_forward_bars is not None:
        return min(remaining_bars, max(1, max_trade_forward_bars))
    chunk = max(_WF_SEQ_MIN_FORWARD_CHUNK_BARS, remaining_bars // 3)
    return min(remaining_bars, chunk)


def _exclude_variation_last_window_single_unresolved(
    klines: list[dict[str, Decimal]],
    trades: list[dict[str, Any]],
    *,
    hours: int = 24,
) -> bool:
    """Igaz, ha a válaszból el kell hagyni: utolsó ``hours`` órában pontosan 1 belépés, nincs TP/SL."""
    if not klines or not trades:
        return False
    end_ms = _to_int_ms(klines[-1]["time"])
    start_ms = end_ms - hours * 60 * 60 * 1000
    recent = [t for t in trades if start_ms <= int(t["entry_time_ms"]) <= end_ms]
    if len(recent) != 1:
        return False
    return recent[0].get("first_touch") == "none"


def _count_trades_with_entry_in_last_hours(
    klines: list[dict[str, Decimal]],
    trades: list[dict[str, Any]],
    *,
    hours: int = 24,
) -> int:
    """Hány trade belépése esik az utolsó gyertya ideje előtti ``hours`` órába (zárt intervallum)."""
    if not klines or not trades:
        return 0
    end_ms = _to_int_ms(klines[-1]["time"])
    start_ms = end_ms - hours * 60 * 60 * 1000
    n = 0
    for t in trades:
        et = int(t["entry_time_ms"])
        if start_ms <= et <= end_ms:
            n += 1
    return n


def _compute_current_signal(
    klines: list[dict[str, Decimal]],
    *,
    choppiness_max: Decimal,
    tp_median_multiplier: Decimal = Decimal("0.5"),
    sl_median_multiplier: Decimal = Decimal("0.5"),
    clip_variation_tpsl_bounds: bool = False,
) -> dict[str, Any]:
    """Teljes eddigi sorozatra: utolsó záró = belépés, TP/SL a train medián × szorzók alapján."""
    empty: dict[str, Any] = {
        "enabled": False,
        "disabled_reason": None,
        "predicted_side": None,
        "prediction_reason": None,
        "entry_price": None,
        "tp_price": None,
        "sl_price": None,
        "median_move_pct_train": None,
        "tp_move_pct": None,
        "sl_move_pct": None,
        "train_bar_count": 0,
    }
    if len(klines) < 5:
        empty["disabled_reason"] = "too_few_candles"
        return empty
    train_clean, train_stats = analyze_clean_legs(klines, choppiness_max=choppiness_max)
    med = train_stats.get("median_move_pct")
    if med is None or not isinstance(med, Decimal) or med <= 0:
        empty["disabled_reason"] = "no_median_clean_legs"
        return empty
    tp_move = med * tp_median_multiplier
    sl_move = med * sl_median_multiplier
    if clip_variation_tpsl_bounds:
        tp_move, sl_move = _clip_variation_tpsl_move_pct(tp_move, sl_move)
    tp_move, sl_move = _coerce_sl_move_pct_le_tp(tp_move, sl_move)
    predicted, reason = predict_side_from_train_clean_legs(klines, train_clean)
    entry = klines[-1]["close"]
    if entry <= 0:
        empty["disabled_reason"] = "invalid_price"
        return empty
    tp, sl = _tp_sl_prices_for_side(entry, tp_move, sl_move, predicted)

    def _q4(x: Decimal) -> str:
        return str(x.quantize(Decimal("0.0001")))

    def _price_str(x: Decimal) -> str:
        return str(x.quantize(Decimal("0.00000001")))

    return {
        "enabled": True,
        "disabled_reason": None,
        "predicted_side": predicted,
        "prediction_reason": reason,
        "entry_price": _price_str(entry),
        "tp_price": _price_str(tp),
        "sl_price": _price_str(sl),
        "median_move_pct_train": _q4(med),
        "tp_move_pct": _q4(tp_move),
        "sl_move_pct": _q4(sl_move),
        "train_bar_count": len(klines),
    }


def _build_walk_forward_sequence_core(
    klines: list[dict[str, Decimal]],
    *,
    choppiness_max: Decimal,
    tp_median_multiplier: Decimal,
    sl_median_multiplier: Decimal,
    initial_split_fraction: Decimal = Decimal("0.5"),
    cooldown_minutes: int = 60,
    min_train: int = 15,
    margin_bars: int = 5,
    max_trades: int = 40,
    clip_variation_tpsl_bounds: bool = False,
    max_trade_forward_bars: int | None = None,
) -> dict[str, Any]:
    """Szekvenciális trade szimuláció: TP/SL távolság = train medián × (tp_mult, sl_mult).

    Egy trade előretekintése alapból max. a hátralévő gyertyák harmada (min.
    ``_WF_SEQ_MIN_FORWARD_CHUNK_BARS``), hogy TP/SL nélküli szakasz ne nyelje el az egész tesztet;
    ``max_trade_forward_bars`` felülírja ezt. A szimulált SL %% távolság soha nem haladja meg a
    TP %% távolságot (``_coerce_sl_move_pct_le_tp``).
    """
    current = _compute_current_signal(
        klines,
        choppiness_max=choppiness_max,
        tp_median_multiplier=tp_median_multiplier,
        sl_median_multiplier=sl_median_multiplier,
        clip_variation_tpsl_bounds=clip_variation_tpsl_bounds,
    )
    base: dict[str, Any] = {
        "enabled": False,
        "disabled_reason": None,
        "cooldown_minutes": cooldown_minutes,
        "initial_split_fraction": str(initial_split_fraction),
        "first_checkpoint_time_ms": None,
        "tp_median_multiplier": str(tp_median_multiplier),
        "sl_median_multiplier": str(sl_median_multiplier),
        "trades": [],
        "summary": None,
        "current_signal": current,
    }

    sp = split_klines_at_time_fraction(
        klines, initial_split_fraction, min_train=min_train, min_test=5
    )
    if sp is None:
        base["disabled_reason"] = "too_few_candles_or_bad_time_span"
        base["enabled"] = bool(current.get("enabled"))
        return base

    _train0, _test0, split_idx = sp
    entry_idx = split_idx - 1
    base["first_checkpoint_time_ms"] = _to_int_ms(klines[entry_idx]["time"])

    trades: list[dict[str, Any]] = []
    n = len(klines)

    def _q4(x: Decimal) -> str:
        return str(x.quantize(Decimal("0.0001")))

    def _price_str(x: Decimal) -> str:
        return str(x.quantize(Decimal("0.00000001")))

    while len(trades) < max_trades:
        train = klines[: entry_idx + 1]
        if len(train) < min_train:
            break
        train_clean, train_stats = analyze_clean_legs(
            train, choppiness_max=choppiness_max
        )
        med = train_stats.get("median_move_pct")
        if med is None or not isinstance(med, Decimal) or med <= 0:
            break
        tp_move = med * tp_median_multiplier
        sl_move = med * sl_median_multiplier
        if clip_variation_tpsl_bounds:
            tp_move, sl_move = _clip_variation_tpsl_move_pct(tp_move, sl_move)
        tp_move, sl_move = _coerce_sl_move_pct_le_tp(tp_move, sl_move)
        predicted, reason = predict_side_from_train_clean_legs(train, train_clean)
        entry = train[-1]["close"]
        if entry <= 0:
            break
        remaining = len(klines) - entry_idx - 1
        if remaining <= 0:
            break
        mf = _trade_forward_window_bars(
            remaining, max_trade_forward_bars=max_trade_forward_bars
        )
        if mf <= 0:
            break
        forward = klines[entry_idx + 1 : entry_idx + 1 + mf]
        touch, off, amb = _simulate_tp_sl(
            forward,
            entry=entry,
            tp_move_pct=tp_move,
            sl_move_pct=sl_move,
            side=predicted,
        )
        if touch in ("tp", "sl") and off is not None:
            exit_idx = entry_idx + 1 + off
            exit_local = off
        else:
            exit_local = len(forward) - 1
            exit_idx = entry_idx + 1 + exit_local

        f0 = forward[0]["close"]
        f1 = forward[exit_local]["close"]
        actual_side: Literal["long", "short"] = "long" if f1 > f0 else "short"
        direction_ok = predicted == actual_side
        tp_price, sl_price = _tp_sl_prices_for_side(entry, tp_move, sl_move, predicted)
        chart_from = max(0, entry_idx - margin_bars)
        chart_to = min(n - 1, exit_idx + margin_bars)
        exit_px = klines[exit_idx]["close"]

        trades.append(
            {
                "trade_index": len(trades),
                "entry_bar_index": entry_idx,
                "exit_bar_index": exit_idx,
                "chart_from_index": chart_from,
                "chart_to_index": chart_to,
                "entry_time_ms": _to_int_ms(klines[entry_idx]["time"]),
                "exit_time_ms": _to_int_ms(klines[exit_idx]["time"]),
                "predicted_side": predicted,
                "prediction_reason": reason,
                "first_touch": touch,
                "entry_price": _price_str(entry),
                "exit_price": _price_str(exit_px),
                "tp_price": _price_str(tp_price),
                "sl_price": _price_str(sl_price),
                "median_move_pct_train": _q4(med),
                "tp_move_pct": _q4(tp_move),
                "sl_move_pct": _q4(sl_move),
                "strategy_would_win": touch == "tp",
                "same_bar_ambiguous": amb,
                "direction_guess_correct": direction_ok,
            }
        )

        nxt = _next_bar_index_after_cooldown(klines, exit_idx, cooldown_minutes)
        if nxt is None:
            break
        entry_idx = nxt

    tp_w = sum(1 for t in trades if t["first_touch"] == "tp")
    sl_l = sum(1 for t in trades if t["first_touch"] == "sl")
    no_r = sum(1 for t in trades if t["first_touch"] == "none")
    dir_h = sum(1 for t in trades if t["direction_guess_correct"])

    summary: dict[str, Any] | None = None
    if trades:
        summary = {
            "total_trades": len(trades),
            "tp_wins": tp_w,
            "sl_losses": sl_l,
            "no_result": no_r,
            "direction_hits": dir_h,
        }

    base["trades"] = trades
    base["summary"] = summary
    base["current_signal"] = _compute_current_signal(
        klines,
        choppiness_max=choppiness_max,
        tp_median_multiplier=tp_median_multiplier,
        sl_median_multiplier=sl_median_multiplier,
        clip_variation_tpsl_bounds=clip_variation_tpsl_bounds,
    )
    base["enabled"] = bool(trades) or bool(base["current_signal"].get("enabled"))
    if not trades and not base["current_signal"].get("enabled"):
        base["disabled_reason"] = "no_trades_and_no_current_signal"
    return base


def build_walk_forward_sequence(
    klines: list[dict[str, Decimal]],
    *,
    choppiness_max: Decimal,
    initial_split_fraction: Decimal = Decimal("0.5"),
    cooldown_minutes: int = 60,
    min_train: int = 15,
    margin_bars: int = 5,
    max_trades: int = 40,
) -> dict[str, Any]:
    """Alapértelmezés: TP és SL egyaránt ``medián × 0.5`` (régi medián/2 viselkedés)."""
    return _build_walk_forward_sequence_core(
        klines,
        choppiness_max=choppiness_max,
        tp_median_multiplier=Decimal("0.5"),
        sl_median_multiplier=Decimal("0.5"),
        initial_split_fraction=initial_split_fraction,
        cooldown_minutes=cooldown_minutes,
        min_train=min_train,
        margin_bars=margin_bars,
        max_trades=max_trades,
    )


def _tpsl_variation_multiplier_pairs() -> list[tuple[Decimal, Decimal]]:
    """TP/SL szorzók a train tiszta-láb mediánjára (rács, deduplikálva)."""
    vals = [
        Decimal("0.25"),
        Decimal("0.35"),
        Decimal("0.5"),
        Decimal("0.65"),
        Decimal("0.75"),
        Decimal("1.0"),
    ]
    out: list[tuple[Decimal, Decimal]] = []
    seen: set[tuple[str, str]] = set()
    for tp in vals:
        for sl in vals:
            key = (str(tp), str(sl))
            if key in seen:
                continue
            seen.add(key)
            out.append((tp, sl))
    return out


def build_walk_forward_tpsl_variations_payload(
    klines: list[dict[str, Decimal]],
    *,
    choppiness_max: Decimal,
    cooldown_minutes: int,
    target_tp_win_rate_pct: Decimal = Decimal("85"),
    min_resolved_trades: int = 2,
) -> dict[str, Any]:
    """Több TP/SL (medián×) kombináció; szimulációban TP/SL %% csak **felülről** vágva (≤300 / ≤150).

    A TP ≥30%% és SL ≥10%% a ``meets_min_tpsl_pct_profile`` mezőben szerepel (első belépés
    train-mediánja × szorzó); **ajánláshoz** kell ez is, különben a rács sorai különbözőek lennének,
    de felfelé klipelés mind ugyanazt a 30/10-et adná. A sorrend: feloldott TP/(TP+SL) csökkenő.
    Kiesnek a sorok, ha az utolsó 24 órában pontosan egy belépés volt és nincs TP/SL.
    **Ajánlott**: első rendezett sor, ahol ≥ ``_WF_MIN_TRADES_LAST_24H_FOR_RECOMMENDATION`` belépés
    volt 24h-ban **és** ``meets_min_tpsl_pct_profile``; csak ekkor ``best_current_signal``.
    """
    pairs = _tpsl_variation_multiplier_pairs()
    rows_raw: list[dict[str, Any]] = []
    for tp_m, sl_m in pairs:
        seq = _build_walk_forward_sequence_core(
            klines,
            choppiness_max=choppiness_max,
            tp_median_multiplier=tp_m,
            sl_median_multiplier=sl_m,
            cooldown_minutes=cooldown_minutes,
            clip_variation_tpsl_bounds=True,
        )
        summ = seq.get("summary")
        tp_w = int(summ["tp_wins"]) if summ else 0
        sl_l = int(summ["sl_losses"]) if summ else 0
        resolved = tp_w + sl_l
        rate: Decimal | None = None
        if resolved >= min_resolved_trades and resolved > 0:
            rate = Decimal(tp_w) / Decimal(resolved) * Decimal(100)
        meets = rate is not None and rate >= target_tp_win_rate_pct
        label = f"TP×{tp_m} med, SL×{sl_m} med"
        slim = {
            "enabled": seq["enabled"],
            "disabled_reason": seq.get("disabled_reason"),
            "cooldown_minutes": seq["cooldown_minutes"],
            "initial_split_fraction": seq["initial_split_fraction"],
            "first_checkpoint_time_ms": seq.get("first_checkpoint_time_ms"),
            "tp_median_multiplier": seq["tp_median_multiplier"],
            "sl_median_multiplier": seq["sl_median_multiplier"],
            "trades": seq["trades"],
            "summary": seq.get("summary"),
        }
        n24 = _count_trades_with_entry_in_last_hours(klines, seq["trades"], hours=24)
        if _exclude_variation_last_window_single_unresolved(
            klines, seq["trades"], hours=24
        ):
            continue
        raw_tp_s: str | None = None
        raw_sl_s: str | None = None
        meets_profile = False
        trs = seq.get("trades") or []
        if trs:
            med0 = Decimal(str(trs[0]["median_move_pct_train"]))
            raw_tp = med0 * tp_m
            raw_sl = med0 * sl_m
            raw_tp_s = str(raw_tp.quantize(Decimal("0.0001")))
            raw_sl_s = str(raw_sl.quantize(Decimal("0.0001")))
            meets_profile = _variation_meets_min_tpsl_pct_profile(raw_tp, raw_sl)
        rows_raw.append(
            {
                "tp_median_multiplier": str(tp_m),
                "sl_median_multiplier": str(sl_m),
                "label": label,
                "resolved_tp_win_rate_pct": (
                    str(rate.quantize(Decimal("0.01"))) if rate is not None else None
                ),
                "meets_target": meets,
                "resolved_count": resolved,
                "trades_entered_last_24h_count": n24,
                "first_trade_tp_move_pct_raw": raw_tp_s,
                "first_trade_sl_move_pct_raw": raw_sl_s,
                "meets_min_tpsl_pct_profile": meets_profile,
                "sequence": slim,
            }
        )

    def _rate_key(r: dict[str, Any]) -> Decimal:
        s = r.get("resolved_tp_win_rate_pct")
        if s is None:
            return Decimal("-1")
        return Decimal(str(s))

    def _tpw(r: dict[str, Any]) -> int:
        s = (r.get("sequence") or {}).get("summary")
        if isinstance(s, dict):
            return int(s.get("tp_wins", 0))
        return 0

    rows_raw.sort(
        key=lambda r: (_rate_key(r), _tpw(r), r.get("resolved_count", 0)),
        reverse=True,
    )

    rec_idx: int | None = None
    for i, r in enumerate(rows_raw):
        if (
            int(r["trades_entered_last_24h_count"])
            < _WF_MIN_TRADES_LAST_24H_FOR_RECOMMENDATION
        ):
            continue
        if not bool(r.get("meets_min_tpsl_pct_profile")):
            continue
        rec_idx = i
        break

    rows: list[dict[str, Any]] = []
    for rank, item in enumerate(rows_raw):
        row = dict(item)
        row["rank"] = rank
        row["is_recommended"] = rec_idx is not None and rank == rec_idx
        rows.append(row)

    any_meets = any(r["meets_target"] for r in rows)
    has_recommended = rec_idx is not None
    best_sig: dict[str, Any] | None = None
    if has_recommended and rows_raw:
        best = rows_raw[rec_idx]
        best_tp = Decimal(best["tp_median_multiplier"])
        best_sl = Decimal(best["sl_median_multiplier"])
        best_sig = _compute_current_signal(
            klines,
            choppiness_max=choppiness_max,
            tp_median_multiplier=best_tp,
            sl_median_multiplier=best_sl,
            clip_variation_tpsl_bounds=True,
        )

    return {
        "enabled": bool(rows),
        "disabled_reason": None if rows else "no_variation_runs",
        "target_tp_win_rate_pct": str(target_tp_win_rate_pct.quantize(Decimal("0.01"))),
        "min_resolved_trades": min_resolved_trades,
        "any_variation_meets_target": any_meets,
        "has_recommended_variation": has_recommended,
        "min_trades_last_24h_for_recommendation": _WF_MIN_TRADES_LAST_24H_FOR_RECOMMENDATION,
        "variation_tp_move_pct_min": str(_WF_VAR_TP_MOVE_PCT_MIN),
        "variation_tp_move_pct_max": str(_WF_VAR_TP_MOVE_PCT_MAX),
        "variation_sl_move_pct_min": str(_WF_VAR_SL_MOVE_PCT_MIN),
        "variation_sl_move_pct_max": str(_WF_VAR_SL_MOVE_PCT_MAX),
        "best_current_signal": best_sig,
        "variations": rows,
    }


def wf_variation_snapshot_from_row(
    row: dict[str, Any], *, target_tp_win_rate_pct: str | None
) -> dict[str, Any]:
    """WF variációs rács-sor kompakt leírása (rendelés ``entry_context``)."""
    return {
        "rank": row.get("rank"),
        "label": row.get("label"),
        "resolved_tp_win_rate_pct": row.get("resolved_tp_win_rate_pct"),
        "meets_target": bool(row.get("meets_target")),
        "meets_min_tpsl_pct_profile": bool(row.get("meets_min_tpsl_pct_profile")),
        "trades_entered_last_24h_count": int(
            row.get("trades_entered_last_24h_count", 0) or 0
        ),
        "resolved_count": int(row.get("resolved_count", 0) or 0),
        "tp_median_multiplier": row.get("tp_median_multiplier"),
        "sl_median_multiplier": row.get("sl_median_multiplier"),
        "target_tp_win_rate_pct": target_tp_win_rate_pct,
    }


def walk_forward_live_gate_from_klines(
    klines: list[dict[str, Decimal]],
    *,
    choppiness_max: Decimal,
    walk_forward_cooldown_minutes: int = 60,
) -> dict[str, Any]:
    """Top signal / live: WF variációs rács + aktuális jel.

    Először a coin-analyze **profil-ajánlása** (``has_recommended_variation``): ≥5 belépés
    / 24h és TP/SL nyers %% ≥ UI minimum (30/10). Ha nincs ilyen (kis medián → kis %%),
    **fallback**: a rangsorban első sor, ahol ``meets_target`` (alapból ≥85% TP win) és
    ≥5 belépés / 24h — ez egyezik a rács tetején látott „jó” variációval.

    Returns:
        ``ok``, ``reason``, siker esetén: ``side``, ``tp_move_pct``, ``sl_move_pct``,
        ``tp_median_multiplier``, ``sl_median_multiplier``, ``prediction_reason``,
        ``wf_gate_source`` (``ui_profile_recommendation`` | ``grid_meets_target``),
        ``wf_variation_snapshot``, ``wf_target_tp_win_rate_pct``.
    """
    vblock = build_walk_forward_tpsl_variations_payload(
        klines,
        choppiness_max=choppiness_max,
        cooldown_minutes=walk_forward_cooldown_minutes,
    )
    if not vblock.get("enabled"):
        return {
            "ok": False,
            "reason": "walk_forward_variations_disabled",
            "detail": vblock.get("disabled_reason"),
        }

    target_tp_raw = vblock.get("target_tp_win_rate_pct")
    wf_target_tp_win_rate_pct: str | None = (
        str(target_tp_raw) if target_tp_raw is not None else None
    )

    sig: dict[str, Any] | None = None
    wf_gate_source: str = ""
    rec_tp: str | None = None
    rec_sl: str | None = None
    selected_row: dict[str, Any] | None = None

    if vblock.get("has_recommended_variation"):
        strict_sig = vblock.get("best_current_signal")
        if isinstance(strict_sig, dict) and strict_sig.get("enabled"):
            sig = strict_sig
            wf_gate_source = "ui_profile_recommendation"
            for row in vblock.get("variations") or []:
                if row.get("is_recommended"):
                    rec_tp = str(row.get("tp_median_multiplier"))
                    rec_sl = str(row.get("sl_median_multiplier"))
                    selected_row = row if isinstance(row, dict) else None
                    break

    if not isinstance(sig, dict) or not sig.get("enabled"):
        rows = sorted(
            (vblock.get("variations") or []),
            key=lambda r: int(r.get("rank", 999)),
        )
        for row in rows:
            if int(row.get("trades_entered_last_24h_count", 0)) < (
                _WF_MIN_TRADES_LAST_24H_FOR_RECOMMENDATION
            ):
                continue
            if not row.get("meets_target"):
                continue
            try:
                best_tp = Decimal(str(row["tp_median_multiplier"]))
                best_sl = Decimal(str(row["sl_median_multiplier"]))
            except (ArithmeticError, ValueError, TypeError):
                continue
            cand = _compute_current_signal(
                klines,
                choppiness_max=choppiness_max,
                tp_median_multiplier=best_tp,
                sl_median_multiplier=best_sl,
                clip_variation_tpsl_bounds=True,
            )
            if isinstance(cand, dict) and cand.get("enabled"):
                sig = cand
                wf_gate_source = "grid_meets_target"
                rec_tp = str(row.get("tp_median_multiplier"))
                rec_sl = str(row.get("sl_median_multiplier"))
                selected_row = row if isinstance(row, dict) else None
                break

    if not isinstance(sig, dict) or not sig.get("enabled") or not wf_gate_source:
        return {"ok": False, "reason": "walk_forward_no_eligible_variation"}
    ps = sig.get("predicted_side")
    side_map = {"long": "BUY", "short": "SELL"}
    if ps not in side_map:
        return {"ok": False, "reason": "walk_forward_invalid_predicted_side"}
    tp_raw = sig.get("tp_move_pct")
    sl_raw = sig.get("sl_move_pct")
    if tp_raw is None or sl_raw is None:
        return {"ok": False, "reason": "walk_forward_missing_move_pct"}
    try:
        tp_move_pct = Decimal(str(tp_raw))
        sl_move_pct = Decimal(str(sl_raw))
    except (ArithmeticError, ValueError, TypeError):
        return {"ok": False, "reason": "walk_forward_move_pct_parse_error"}
    if tp_move_pct <= 0 or sl_move_pct <= 0:
        return {"ok": False, "reason": "walk_forward_non_positive_moves"}

    wf_variation_snapshot = (
        wf_variation_snapshot_from_row(
            selected_row, target_tp_win_rate_pct=wf_target_tp_win_rate_pct
        )
        if isinstance(selected_row, dict)
        else None
    )

    return {
        "ok": True,
        "reason": "walk_forward_recommended",
        "side": side_map[ps],
        "tp_move_pct": tp_move_pct,
        "sl_move_pct": sl_move_pct,
        "tp_median_multiplier": rec_tp,
        "sl_median_multiplier": rec_sl,
        "prediction_reason": sig.get("prediction_reason"),
        "wf_gate_source": wf_gate_source,
        "wf_variation_snapshot": wf_variation_snapshot,
        "wf_target_tp_win_rate_pct": wf_target_tp_win_rate_pct,
    }


_WF_AGGREGATE_FRACTIONS: tuple[Decimal, ...] = (
    Decimal("0.36"),
    Decimal("0.40"),
    Decimal("0.44"),
    Decimal("0.48"),
    Decimal("0.52"),
    Decimal("0.56"),
    Decimal("0.60"),
)


def run_walk_forward_simulation(
    train: list[dict[str, Decimal]],
    test: list[dict[str, Decimal]],
    *,
    choppiness_max: Decimal,
    time_split_fraction: Decimal,
) -> dict[str, Any] | None:
    """Egy train/test párra walk-forward eredmény, vagy ``None`` ha nincs train medián."""
    train_clean, train_stats = analyze_clean_legs(train, choppiness_max=choppiness_max)
    med = train_stats.get("median_move_pct")
    if med is None or not isinstance(med, Decimal) or med <= 0:
        return None

    half_med = med / Decimal(2)
    predicted, reason = predict_side_from_train_clean_legs(train, train_clean)
    entry = train[-1]["close"]

    t_open = test[0]["close"]
    t_close = test[-1]["close"]
    if t_open <= 0:
        return None

    if predicted == "long":
        tp_price = entry * (Decimal(1) + half_med / Decimal(100))
        sl_price = entry * (Decimal(1) - half_med / Decimal(100))
    else:
        tp_price = entry * (Decimal(1) - half_med / Decimal(100))
        sl_price = entry * (Decimal(1) + half_med / Decimal(100))

    test_net = (t_close - t_open) / t_open * Decimal(100)
    actual_side: Literal["long", "short"] = "long" if t_close > t_open else "short"
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

    def _price_str(x: Decimal) -> str:
        return str(x.quantize(Decimal("0.00000001")))

    return {
        "enabled": True,
        "disabled_reason": None,
        "time_split_fraction": str(time_split_fraction),
        "train_start_time_ms": _to_int_ms(train[0]["time"]),
        "train_end_time_ms": _to_int_ms(train[-1]["time"]),
        "checkpoint_time_ms": _to_int_ms(train[-1]["time"]),
        "test_start_time_ms": _to_int_ms(test[0]["time"]),
        "test_end_time_ms": _to_int_ms(test[-1]["time"]),
        "train_bar_count": len(train),
        "test_bar_count": len(test),
        "median_move_pct_train": _q4(med),
        "tp_move_pct": _q4(half_med),
        "sl_move_pct": _q4(half_med),
        "entry_price": _price_str(entry),
        "tp_price": _price_str(tp_price),
        "sl_price": _price_str(sl_price),
        "test_start_close": _price_str(t_open),
        "test_end_close": _price_str(t_close),
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


def _build_walk_forward_aggregate(
    klines: list[dict[str, Decimal]],
    *,
    choppiness_max: Decimal,
) -> dict[str, Any] | None:
    """Több időbeli vágási aránynál ugyanaz a szabály — összesített találati arány."""
    tp_c = sl_c = none_c = dir_c = 0
    total = 0
    for frac in _WF_AGGREGATE_FRACTIONS:
        if frac == Decimal("0.5"):
            continue
        sp = split_klines_at_time_fraction(klines, frac)
        if sp is None:
            continue
        tr, te, _ = sp
        one = run_walk_forward_simulation(
            tr, te, choppiness_max=choppiness_max, time_split_fraction=frac
        )
        if one is None:
            continue
        total += 1
        if one["direction_guess_correct"]:
            dir_c += 1
        ft = one["first_touch"]
        if ft == "tp":
            tp_c += 1
        elif ft == "sl":
            sl_c += 1
        else:
            none_c += 1
    if total == 0:
        return None
    resolved = tp_c + sl_c
    win_rate: Decimal | None = None
    if resolved > 0:
        win_rate = Decimal(tp_c) / Decimal(resolved) * Decimal(100)
    dir_rate = Decimal(dir_c) / Decimal(total) * Decimal(100)

    def _q2(x: Decimal) -> str:
        return str(x.quantize(Decimal("0.01")))

    return {
        "total_runs": total,
        "tp_first_count": tp_c,
        "sl_first_count": sl_c,
        "no_touch_count": none_c,
        "direction_correct_count": dir_c,
        "strategy_win_rate_pct": (_q2(win_rate) if win_rate is not None else None),
        "direction_hit_rate_pct": _q2(dir_rate),
    }


def build_walk_forward_payload(
    klines: list[dict[str, Decimal]],
    *,
    choppiness_max: Decimal = Decimal("1.72"),
) -> dict[str, Any]:
    """Walk-forward: fő szcenárió idő felezés (0.5), plusz több vágás aggregátum."""
    base: dict[str, Any] = {
        "enabled": False,
        "disabled_reason": None,
        "time_split_fraction": None,
        "train_start_time_ms": None,
        "train_end_time_ms": None,
        "checkpoint_time_ms": None,
        "test_start_time_ms": None,
        "test_end_time_ms": None,
        "train_bar_count": 0,
        "test_bar_count": 0,
        "median_move_pct_train": None,
        "tp_move_pct": None,
        "sl_move_pct": None,
        "entry_price": None,
        "tp_price": None,
        "sl_price": None,
        "test_start_close": None,
        "test_end_close": None,
        "predicted_side": None,
        "prediction_reason": None,
        "test_net_move_pct": None,
        "actual_test_side": None,
        "direction_guess_correct": None,
        "first_touch": None,
        "first_touch_time_ms": None,
        "same_bar_ambiguous": None,
        "strategy_would_win": None,
        "aggregate": _build_walk_forward_aggregate(
            klines, choppiness_max=choppiness_max
        ),
    }

    sp = split_klines_at_time_fraction(klines, Decimal("0.5"))
    if sp is None:
        base["disabled_reason"] = "too_few_candles_or_bad_time_span"
        return base

    train, test, _ = sp
    primary = run_walk_forward_simulation(
        train,
        test,
        choppiness_max=choppiness_max,
        time_split_fraction=Decimal("0.5"),
    )
    if primary is None:
        base["disabled_reason"] = "no_median_clean_legs_in_train"
        base["train_bar_count"] = len(train)
        base["test_bar_count"] = len(test)
        base["checkpoint_time_ms"] = _to_int_ms(train[-1]["time"])
        base["train_start_time_ms"] = _to_int_ms(train[0]["time"])
        base["train_end_time_ms"] = _to_int_ms(train[-1]["time"])
        if test:
            base["test_start_time_ms"] = _to_int_ms(test[0]["time"])
            base["test_end_time_ms"] = _to_int_ms(test[-1]["time"])
        return base

    base.update(primary)
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
    walk_forward_cooldown_minutes: int = 60,
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
        "walk_forward_sequence": build_walk_forward_sequence(
            klines,
            choppiness_max=choppiness_max,
            cooldown_minutes=walk_forward_cooldown_minutes,
        ),
        "walk_forward_tpsl_variations": build_walk_forward_tpsl_variations_payload(
            klines,
            choppiness_max=choppiness_max,
            cooldown_minutes=walk_forward_cooldown_minutes,
        ),
    }
