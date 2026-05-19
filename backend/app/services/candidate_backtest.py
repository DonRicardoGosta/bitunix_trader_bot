"""7 napos, :15 belépéses TP/SL backtest a top mozgó coinok szűréséhez.

Minden variáció fix margin-ROI TP/SL párokkal fut; csak TP és SL zárhat
(nincs időzített kilépés). A coin akkor minősül jelöltnek, ha legalább egy
variáció ≥80%% TP win rate-et ad (feloldatlan trade nem számít sikernek).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from app.services.coin_analyze import (
    _compute_tp_win_rate_pct,
    _simulate_tp_sl,
    _to_int_ms,
    analyze_clean_legs,
    predict_side_from_train_clean_legs,
)
from app.services.tpsl import implied_price_move_pct_from_roi

BACKTEST_LOOKBACK_DAYS = 7
BACKTEST_TARGET_WIN_RATE_PCT = Decimal("80")
BACKTEST_MIN_TRADES = 2
# Fallback, ha nincs trading_pairs meta (kalibráció ilyen coin-t kihagy).
BACKTEST_REFERENCE_LEVERAGE = 20
BACKTEST_ENTRY_MINUTE = 15
BACKTEST_MIN_TRAIN_BARS = 15

# Fix TP/SL margin ROI %% párok (tp, sl) — a felhasználói spec szerint.
TPSL_ROI_VARIATIONS: list[tuple[Decimal, Decimal, str]] = [
    (Decimal("50"), Decimal("50"), "TP50/SL50"),
    (Decimal("100"), Decimal("50"), "TP100/SL50"),
    (Decimal("150"), Decimal("100"), "TP150/SL100"),
    (Decimal("200"), Decimal("100"), "TP200/SL100"),
]


def bar_datetime_utc(kline: dict[str, Decimal]) -> datetime:
    """Gyertya időbélyeg UTC ``datetime``-ként (ms vagy s)."""
    ms = _to_int_ms(kline["time"])
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def is_hour_quarter_entry_bar(kline: dict[str, Decimal], *, minute: int = 15) -> bool:
    """Igaz, ha a gyertya zárása a megadott percen van (alap: :15)."""
    return bar_datetime_utc(kline).minute == minute


def entry_bar_indices(
    klines: list[dict[str, Decimal]],
    *,
    minute: int = BACKTEST_ENTRY_MINUTE,
    min_train: int = BACKTEST_MIN_TRAIN_BARS,
) -> list[int]:
    """Indexek, ahol új belépés engedélyezett (:15 gyertyák, elég train után)."""
    out: list[int] = []
    for i, k in enumerate(klines):
        if i < min_train:
            continue
        if is_hour_quarter_entry_bar(k, minute=minute):
            out.append(i)
    return out


def simulate_variation_on_klines(
    klines: list[dict[str, Decimal]],
    *,
    tp_roi_pct: Decimal,
    sl_roi_pct: Decimal,
    leverage: int = BACKTEST_REFERENCE_LEVERAGE,
    choppiness_max: Decimal = Decimal("1.72"),
    entry_minute: int = BACKTEST_ENTRY_MINUTE,
) -> dict[str, Any]:
    """Egy TP/SL ROI párra teljes 7 napos szimuláció (:15 belépések, csak TP/SL zárás)."""
    tp_move, sl_move = implied_price_move_pct_from_roi(
        leverage=leverage,
        tp_roi_pct=tp_roi_pct,
        sl_roi_pct=sl_roi_pct,
    )
    entries = entry_bar_indices(klines, minute=entry_minute)
    trades: list[dict[str, Any]] = []
    cursor = 0

    while cursor < len(entries):
        entry_idx = entries[cursor]
        train = klines[: entry_idx + 1]
        train_clean, _ = analyze_clean_legs(train, choppiness_max=choppiness_max)
        predicted, reason = predict_side_from_train_clean_legs(train, train_clean)
        entry = train[-1]["close"]
        if entry <= 0:
            cursor += 1
            continue

        forward = klines[entry_idx + 1 :]
        if not forward:
            break

        touch, off, amb = _simulate_tp_sl(
            forward,
            entry=entry,
            tp_move_pct=tp_move,
            sl_move_pct=sl_move,
            side=predicted,
        )

        if touch in ("tp", "sl") and off is not None:
            exit_idx = entry_idx + 1 + off
        else:
            exit_idx = entry_idx + len(forward)

        trades.append(
            {
                "entry_bar_index": entry_idx,
                "exit_bar_index": exit_idx,
                "entry_time_ms": _to_int_ms(klines[entry_idx]["time"]),
                "exit_time_ms": _to_int_ms(klines[exit_idx]["time"]),
                "predicted_side": predicted,
                "prediction_reason": reason,
                "first_touch": touch,
                "same_bar_ambiguous": amb,
                "tp_roi_pct": str(tp_roi_pct),
                "sl_roi_pct": str(sl_roi_pct),
                "tp_move_pct": str(tp_move.quantize(Decimal("0.0001"))),
                "sl_move_pct": str(sl_move.quantize(Decimal("0.0001"))),
            }
        )

        nxt_entry = exit_idx + 1
        while cursor < len(entries) and entries[cursor] < nxt_entry:
            cursor += 1

    tp_w = sum(1 for t in trades if t["first_touch"] == "tp")
    sl_l = sum(1 for t in trades if t["first_touch"] == "sl")
    no_r = sum(1 for t in trades if t["first_touch"] == "none")
    rate = _compute_tp_win_rate_pct(
        tp_w, sl_l, no_r, min_trades=BACKTEST_MIN_TRADES
    )
    meets = rate is not None and rate >= BACKTEST_TARGET_WIN_RATE_PCT

    return {
        "tp_roi_pct": str(tp_roi_pct),
        "sl_roi_pct": str(sl_roi_pct),
        "label": f"TP{tp_roi_pct}/SL{sl_roi_pct}",
        "trades": trades,
        "summary": {
            "total_trades": len(trades),
            "tp_wins": tp_w,
            "sl_losses": sl_l,
            "no_result": no_r,
        },
        "resolved_tp_win_rate_pct": (
            str(rate.quantize(Decimal("0.01"))) if rate is not None else None
        ),
        "meets_target": meets,
    }


def evaluate_symbol_variations(
    klines: list[dict[str, Decimal]],
    *,
    choppiness_max: Decimal = Decimal("1.72"),
    leverage: int = BACKTEST_REFERENCE_LEVERAGE,
) -> dict[str, Any]:
    """Minden fix TP/SL variáció + legjobb ≥80%% találat (ha van)."""
    if len(klines) < BACKTEST_MIN_TRAIN_BARS + 5:
        return {
            "ok": False,
            "reason": "insufficient_klines",
            "variations": [],
            "best_variation": None,
        }

    rows: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    for tp_roi, sl_roi, _label in TPSL_ROI_VARIATIONS:
        row = simulate_variation_on_klines(
            klines,
            tp_roi_pct=tp_roi,
            sl_roi_pct=sl_roi,
            leverage=leverage,
            choppiness_max=choppiness_max,
        )
        slim = {
            "label": row["label"],
            "tp_roi_pct": row["tp_roi_pct"],
            "sl_roi_pct": row["sl_roi_pct"],
            "resolved_tp_win_rate_pct": row["resolved_tp_win_rate_pct"],
            "meets_target": row["meets_target"],
            "summary": row["summary"],
        }
        rows.append(slim)
        if row["meets_target"]:
            rate_s = row["resolved_tp_win_rate_pct"]
            if best is None:
                best = {**slim, "trades_count": row["summary"]["total_trades"]}
            else:
                cur = Decimal(rate_s or "0")
                prev = Decimal(best.get("resolved_tp_win_rate_pct") or "0")
                if cur > prev:
                    best = {**slim, "trades_count": row["summary"]["total_trades"]}

    return {
        "ok": best is not None,
        "reason": "qualified" if best else "no_variation_meets_target",
        "variations": rows,
        "best_variation": best,
    }


def _leverage_run_score(best: dict[str, Any] | None) -> tuple[int, Decimal, int]:
    """Összehasonlításhoz: (qualifikált?, win rate %, trade szám) — nagyobb jobb."""
    if best is None:
        return (0, Decimal("-1"), 0)
    rate_raw = best.get("resolved_tp_win_rate_pct")
    rate = Decimal(str(rate_raw)) if rate_raw is not None else Decimal("-1")
    qualified = 1 if best.get("meets_target") or rate >= BACKTEST_TARGET_WIN_RATE_PCT else 0
    trades = int((best.get("summary") or {}).get("total_trades", 0))
    return (qualified, rate, trades)


def evaluate_symbol_best_leverage(
    klines: list[dict[str, Decimal]],
    *,
    pair_max_leverage: int,
    choppiness_max: Decimal = Decimal("1.72"),
) -> dict[str, Any]:
    """Backtest 20× és párhoz max. leverage mellett; a jobb eredményt adja vissza.

    A kiválasztott leverage mező: ``selected_leverage``. A futások összehasonlítása:
    ``leverage_runs`` (audit / summary).
    """
    from app.services.risk import effective_order_leverage

    ref = BACKTEST_REFERENCE_LEVERAGE
    max_eff = effective_order_leverage(pair_max_leverage)
    levers: list[int] = [ref]
    if max_eff != ref:
        levers.append(max_eff)

    runs: list[dict[str, Any]] = []
    for lev in levers:
        ev = evaluate_symbol_variations(
            klines,
            choppiness_max=choppiness_max,
            leverage=lev,
        )
        runs.append({"leverage": lev, "evaluation": ev})

    best_run = runs[0]
    best_key = _leverage_run_score(runs[0]["evaluation"].get("best_variation"))
    for run in runs[1:]:
        key = _leverage_run_score(run["evaluation"].get("best_variation"))
        if key > best_key:
            best_key = key
            best_run = run

    chosen_ev = best_run["evaluation"]
    leverage_runs = [
        {
            "leverage": r["leverage"],
            "ok": bool(r["evaluation"].get("ok")),
            "reason": r["evaluation"].get("reason"),
            "best_win_rate_pct": (
                (r["evaluation"].get("best_variation") or {}).get(
                    "resolved_tp_win_rate_pct"
                )
            ),
            "best_variation_label": (
                (r["evaluation"].get("best_variation") or {}).get("label")
            ),
        }
        for r in runs
    ]
    return {
        **chosen_ev,
        "selected_leverage": int(best_run["leverage"]),
        "leverage_runs": leverage_runs,
    }


@dataclass(frozen=True)
class QualifiedCandidate:
    """Egy backtesten átment coin + ajánlott TP/SL ROI."""

    symbol: str
    rank: int
    abs_change_24h_pct: Decimal
    tp_roi_pct: Decimal
    sl_roi_pct: Decimal
    win_rate_pct: Decimal
    variation_label: str
    trade_count: int
    variations: list[dict[str, Any]]
    leverage: int
    pair_max_leverage: int | None = None

    def to_summary_dict(self) -> dict[str, Any]:
        tp_move, sl_move = implied_price_move_pct_from_roi(
            leverage=self.leverage,
            tp_roi_pct=self.tp_roi_pct,
            sl_roi_pct=self.sl_roi_pct,
        )
        out: dict[str, Any] = {
            "symbol": self.symbol,
            "rank": self.rank,
            "abs_change_24h_pct": str(self.abs_change_24h_pct),
            "tp_roi_pct": str(self.tp_roi_pct),
            "sl_roi_pct": str(self.sl_roi_pct),
            "tp_move_pct": str(tp_move.quantize(Decimal("0.0001"))),
            "sl_move_pct": str(sl_move.quantize(Decimal("0.0001"))),
            "backtest_win_rate_pct": str(self.win_rate_pct),
            "variation_label": self.variation_label,
            "trade_count": self.trade_count,
            "variations": self.variations,
            "leverage": self.leverage,
        }
        if self.pair_max_leverage is not None:
            out["pair_max_leverage"] = self.pair_max_leverage
        return out
