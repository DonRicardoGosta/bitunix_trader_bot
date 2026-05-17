"""Hold-window optimalizálás: időalapú kilépés szimuláció és legjobb tartam választás.

A 30–60 perces rácsban (5 perces lépéssel) azt méri, hogy egy trade
TP/SL érintése vagy a tartási idő lejárta után mennyi a **ár-mozgás %%**
(long: (exit-entry)/entry×100). Ha a profit ≥ küszöb (alap 15%%), a trade „jó”.

A modul a walk-forward variációk, a kalibráció és az élő időzített kilépés
közös alapja.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

Side = Literal["long", "short"]
ExitKind = Literal["tp", "sl", "time", "open"]


@dataclass(frozen=True)
class HoldWindowParams:
    """Konfigurálható hold-window rács és küszöb."""

    enabled: bool = False
    min_minutes: int = 30
    max_minutes: int = 60
    step_minutes: int = 5
    profit_threshold_pct: Decimal = Decimal("15")

    def grid_minutes(self) -> list[int]:
        if not self.enabled:
            return []
        step = max(1, int(self.step_minutes))
        lo = max(1, int(self.min_minutes))
        hi = max(lo, int(self.max_minutes))
        out: list[int] = []
        m = lo
        while m <= hi:
            out.append(m)
            m += step
        return out


def effective_hold_grid_minutes(
    params: HoldWindowParams,
    *,
    kline_bar_minutes: int,
) -> list[int]:
    """Rács szűrése gyertya-felbontásra: csak olyan percek, amik gyertyán mérhetők.

    15 perces gyertyánál a 35–55 perces lépések gyakran ugyanarra a záró
    gyertyára esnek, mint a 30/45/60 – ezért csak a ``bar`` többszörösei
    maradnak (pl. 30, 45, 60).
    """
    configured = params.grid_minutes()
    if not configured:
        return []
    bar_m = max(1, int(kline_bar_minutes))
    if bar_m <= int(params.step_minutes):
        return configured
    return [m for m in configured if m % bar_m == 0]


def signed_profit_move_pct(
    *,
    entry: Decimal,
    exit_price: Decimal,
    side: Side,
) -> Decimal:
    """Pozíció irány szerinti profit ár-mozgás %% (pozitív = jó)."""
    if entry <= 0:
        return Decimal(0)
    raw = (exit_price - entry) / entry * Decimal(100)
    if side == "short":
        raw = -raw
    return raw


def is_good_profit(profit_move_pct: Decimal, *, threshold_pct: Decimal) -> bool:
    return profit_move_pct >= threshold_pct


def _bar_hit_tp_sl(
    bar: dict[str, Decimal],
    *,
    entry: Decimal,
    tp_price: Decimal,
    sl_price: Decimal,
    side: Side,
) -> tuple[ExitKind | None, bool]:
    """Egy gyertyán TP/SL érintés; ha mindkettő, konzervatív SL."""
    hi, lo = bar["high"], bar["low"]
    if side == "long":
        tp_hit = hi >= tp_price
        sl_hit = lo <= sl_price
    else:
        tp_hit = lo <= tp_price
        sl_hit = hi >= sl_price
    if tp_hit and sl_hit:
        return "sl", True
    if sl_hit:
        return "sl", False
    if tp_hit:
        return "tp", False
    return None, False


def simulate_trade_exit_with_hold(
    forward_bars: list[dict[str, Decimal]],
    *,
    entry_time_ms: int,
    entry: Decimal,
    side: Side,
    tp_move_pct: Decimal,
    sl_move_pct: Decimal,
    hold_minutes: int,
) -> tuple[ExitKind, Decimal, int, bool]:
    """Trade kilépés: TP → SL → idő (hold_minutes) záró áron.

    Returns:
        ``(exit_kind, profit_move_pct, exit_bar_offset, same_bar_ambiguous)``.
        ``exit_bar_offset`` a ``forward_bars`` indexe (0-based).
    """
    if entry <= 0 or not forward_bars:
        return "open", Decimal(0), 0, False
    m_tp = tp_move_pct / Decimal(100)
    m_sl = sl_move_pct / Decimal(100)
    if side == "long":
        tp_price = entry * (Decimal(1) + m_tp)
        sl_price = entry * (Decimal(1) - m_sl)
    else:
        tp_price = entry * (Decimal(1) - m_tp)
        sl_price = entry * (Decimal(1) + m_sl)

    hold_ms = hold_minutes * 60 * 1000
    deadline_ms = entry_time_ms + hold_ms

    for i, bar in enumerate(forward_bars):
        kind, amb = _bar_hit_tp_sl(
            bar,
            entry=entry,
            tp_price=tp_price,
            sl_price=sl_price,
            side=side,
        )
        if kind == "tp":
            return (
                "tp",
                signed_profit_move_pct(entry=entry, exit_price=tp_price, side=side),
                i,
                amb,
            )
        if kind == "sl":
            return (
                "sl",
                signed_profit_move_pct(entry=entry, exit_price=sl_price, side=side),
                i,
                amb,
            )
        bar_ms = int(bar["time"])
        if bar_ms >= deadline_ms:
            exit_px = bar["close"]
            return (
                "time",
                signed_profit_move_pct(entry=entry, exit_price=exit_px, side=side),
                i,
                False,
            )

    last = forward_bars[-1]
    return (
        "time",
        signed_profit_move_pct(entry=entry, exit_price=last["close"], side=side),
        len(forward_bars) - 1,
        False,
    )


def _to_int_ms(t: Decimal | int) -> int:
    if isinstance(t, int):
        return t
    return int(t)


def evaluate_hold_window_grid(
    klines: list[dict[str, Decimal]],
    trades: list[dict[str, Any]],
    *,
    params: HoldWindowParams,
    kline_bar_minutes: int = 1,
) -> dict[str, Any]:
    """Minden hold percre: hány trade „jó” (profit ≥ küszöb a kilépéskor).

    A ``trades`` elemek a WF szekvencia mezőit használják (entry_bar_index,
    predicted_side, tp_move_pct, sl_move_pct).
    """
    configured_grid = params.grid_minutes()
    bar_m = max(1, int(kline_bar_minutes))
    grid = effective_hold_grid_minutes(params, kline_bar_minutes=bar_m)
    coarse = bar_m > int(params.step_minutes)
    empty: dict[str, Any] = {
        "enabled": params.enabled,
        "profit_threshold_pct": str(params.profit_threshold_pct),
        "configured_grid_minutes": configured_grid,
        "grid_minutes": grid,
        "kline_bar_minutes": bar_m,
        "coarse_kline_resolution": coarse,
        "best_hold_minutes": None,
        "best_good_rate_pct": None,
        "rows": [],
    }
    if not params.enabled or not grid or not trades:
        return empty

    threshold = params.profit_threshold_pct
    rows: list[dict[str, Any]] = []

    for hold_m in grid:
        good = 0
        resolved = 0
        for t in trades:
            entry_idx = int(t["entry_bar_index"])
            side_raw = str(t.get("predicted_side", "long"))
            side: Side = "long" if side_raw == "long" else "short"
            try:
                entry = Decimal(str(t["entry_price"]))
                tp_move = Decimal(str(t["tp_move_pct"]))
                sl_move = Decimal(str(t["sl_move_pct"]))
            except (ArithmeticError, TypeError, ValueError):
                continue
            entry_ms = int(t.get("entry_time_ms") or _to_int_ms(klines[entry_idx]["time"]))
            remaining = len(klines) - entry_idx - 1
            if remaining <= 0:
                continue
            forward = klines[entry_idx + 1 :]
            kind, profit, _off, _amb = simulate_trade_exit_with_hold(
                forward,
                entry_time_ms=entry_ms,
                entry=entry,
                side=side,
                tp_move_pct=tp_move,
                sl_move_pct=sl_move,
                hold_minutes=hold_m,
            )
            resolved += 1
            if kind == "tp" or is_good_profit(profit, threshold_pct=threshold):
                good += 1

        rate: Decimal | None = None
        if resolved > 0:
            rate = Decimal(good) / Decimal(resolved) * Decimal(100)
        rows.append(
            {
                "hold_minutes": hold_m,
                "trades_evaluated": resolved,
                "good_trades": good,
                "good_rate_pct": (
                    str(rate.quantize(Decimal("0.01"))) if rate is not None else None
                ),
            }
        )

    best_m: int | None = None
    best_rate: Decimal | None = None
    for row in rows:
        s = row.get("good_rate_pct")
        if s is None:
            continue
        rate = Decimal(str(s))
        if best_rate is None or rate > best_rate:
            best_rate = rate
            best_m = int(row["hold_minutes"])
        elif best_rate is not None and rate == best_rate and best_m is not None:
            if int(row["hold_minutes"]) < best_m:
                best_m = int(row["hold_minutes"])

    return {
        "enabled": True,
        "profit_threshold_pct": str(threshold),
        "configured_grid_minutes": configured_grid,
        "grid_minutes": grid,
        "kline_bar_minutes": bar_m,
        "coarse_kline_resolution": coarse,
        "best_hold_minutes": best_m,
        "best_good_rate_pct": (
            str(best_rate.quantize(Decimal("0.01"))) if best_rate is not None else None
        ),
        "rows": rows,
    }


def optimize_hold_window_for_sequence(
    klines: list[dict[str, Decimal]],
    sequence: dict[str, Any],
    *,
    params: HoldWindowParams,
    kline_bar_minutes: int = 1,
) -> dict[str, Any]:
    """WF szekvencia trade listájára hold-window rács."""
    trades = sequence.get("trades") or []
    return evaluate_hold_window_grid(
        klines, trades, params=params, kline_bar_minutes=kline_bar_minutes
    )


def infer_kline_bar_minutes(klines: list[dict[str, Decimal]]) -> int:
    """Közelítő gyertya-hossz két szomszédos időbélyeg különbségéből."""
    if len(klines) < 2:
        return 1
    t0 = _to_int_ms(klines[0]["time"])
    t1 = _to_int_ms(klines[1]["time"])
    delta_ms = abs(t1 - t0)
    return max(1, delta_ms // 60_000)


def hold_window_from_strategy_config(cfg: Any) -> HoldWindowParams:
    """``TopSignalEntriesConfig`` → ``HoldWindowParams``."""
    return HoldWindowParams(
        enabled=bool(getattr(cfg, "hold_window_optimization_enabled", False)),
        min_minutes=int(getattr(cfg, "hold_window_min_minutes", 30)),
        max_minutes=int(getattr(cfg, "hold_window_max_minutes", 60)),
        step_minutes=int(getattr(cfg, "hold_window_step_minutes", 5)),
        profit_threshold_pct=Decimal(
            str(getattr(cfg, "hold_profit_threshold_pct", "15"))
        ),
    )
