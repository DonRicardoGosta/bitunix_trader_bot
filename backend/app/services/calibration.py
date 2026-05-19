"""TP/SL jelölt-kalibráció (7 napos backtest, :15 belépés).

Algoritmus röviden:
1. Top ``scan_limit`` (alap 200) abszolút 24h mozgó szimbólum, egyesével a
   legnagyobbtól.
2. Mindegyikre 7 nap 15 perces kline (paginált lekérés).
3. Fix TP/SL margin-ROI variációk (50/50, 100/50, 150/100, 200/100) – csak
   TP és SL zárhat; belépés csak óránként :15-kor.
4. Ha legalább egy variáció ≥80%% TP win rate → jelölt (max. ``candidates_target``).
5. Minden scan-elt coin eredménye a ``tpsl_calibration_symbol_runs`` táblában;
   a summary csak összesítő + ``qualified_candidates`` (stratégia / UI).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from statistics import median
from typing import Any

from app.bitunix.client import BitunixClient
from app.bitunix.exceptions import BitunixAPIError, BitunixSignatureError
from app.services.calibration_symbol_runs import (
    SymbolRunDraft,
    draft_from_evaluation,
    draft_from_fetch_failure,
    persist_symbol_run_committed,
)
from app.services.hold_window import HoldWindowParams, optimize_hold_window_for_sequence
from app.services.tpsl import implied_price_move_pct_from_roi


@dataclass
class SymbolCalibration:
    """Egy szimbólum kalibrációs eredménye (backtest jelölt)."""

    symbol: str
    tp_move_pct: Decimal
    sl_move_pct: Decimal
    atr_pct: Decimal
    samples: int
    last_close: Decimal
    abs_change_24h_pct: Decimal
    best_hold_minutes: int | None = None
    hold_good_rate_pct: Decimal | None = None
    tp_roi_pct: Decimal | None = None
    sl_roi_pct: Decimal | None = None
    backtest_win_rate_pct: Decimal | None = None
    variation_label: str | None = None
    backtest_variations: list[dict[str, Any]] | None = None


@dataclass
class CalibrationResult:
    """Egy kalibrációs lefutás teljes eredménye."""

    started_at: datetime
    finished_at: datetime | None = None
    per_symbol: dict[str, SymbolCalibration] = field(default_factory=dict)
    global_tp_move_pct: Decimal | None = None
    global_sl_move_pct: Decimal | None = None
    failed_symbols: list[dict[str, Any]] = field(default_factory=list)
    symbol_run_drafts: list[SymbolRunDraft] = field(default_factory=list)
    qualified_candidates: list[dict[str, Any]] = field(default_factory=list)
    lookback_minutes: int = 120
    top_n: int = 20
    tp_atr_mult: Decimal = Decimal("3.0")
    sl_atr_mult: Decimal = Decimal("1.5")
    candidates_target: int = 0
    candidates_found: int = 0
    scanned_symbols: int = 0
    mode: str = "candidate_backtest"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "lookback_minutes": self.lookback_minutes,
            "top_n": self.top_n,
            "candidates_target": self.candidates_target,
            "candidates_found": self.candidates_found,
            "scanned_symbols": self.scanned_symbols,
            "qualified_candidates": self.qualified_candidates,
            "tp_atr_mult": str(self.tp_atr_mult),
            "sl_atr_mult": str(self.sl_atr_mult),
            "global": {
                "tp_move_pct": (
                    str(self.global_tp_move_pct)
                    if self.global_tp_move_pct is not None
                    else None
                ),
                "sl_move_pct": (
                    str(self.global_sl_move_pct)
                    if self.global_sl_move_pct is not None
                    else None
                ),
                "symbol_count": len(self.per_symbol),
            },
            "per_symbol": {
                sym: {
                    "tp_move_pct": str(s.tp_move_pct),
                    "sl_move_pct": str(s.sl_move_pct),
                    "atr_pct": str(s.atr_pct),
                    "samples": s.samples,
                    "last_close": str(s.last_close),
                    "abs_change_24h_pct": str(s.abs_change_24h_pct),
                    "best_hold_minutes": s.best_hold_minutes,
                    "hold_good_rate_pct": (
                        str(s.hold_good_rate_pct)
                        if s.hold_good_rate_pct is not None
                        else None
                    ),
                    "tp_roi_pct": (
                        str(s.tp_roi_pct) if s.tp_roi_pct is not None else None
                    ),
                    "sl_roi_pct": (
                        str(s.sl_roi_pct) if s.sl_roi_pct is not None else None
                    ),
                    "backtest_win_rate_pct": (
                        str(s.backtest_win_rate_pct)
                        if s.backtest_win_rate_pct is not None
                        else None
                    ),
                    "variation_label": s.variation_label,
                    "backtest_variations": s.backtest_variations,
                }
                for sym, s in self.per_symbol.items()
            },
            "failed_symbols": (
                self.failed_symbols if not self.symbol_run_drafts else []
            ),
            "symbol_runs_count": len(self.symbol_run_drafts),
            "symbol_runs_table": "tpsl_calibration_symbol_runs",
        }

    def lookup(self, symbol: str) -> tuple[Decimal, Decimal] | None:
        """Per-symbol TP/SL ha van, különben globális fallback, különben None."""
        s = self.per_symbol.get(symbol)
        if s is not None:
            return s.tp_move_pct, s.sl_move_pct
        if (
            self.global_tp_move_pct is not None
            and self.global_sl_move_pct is not None
        ):
            return self.global_tp_move_pct, self.global_sl_move_pct
        return None

    def lookup_hold_minutes(self, symbol: str) -> int | None:
        """Optimális tartási idő percben, ha a hold-window kalibráció futott."""
        s = self.per_symbol.get(symbol)
        if s is not None and s.best_hold_minutes is not None:
            return s.best_hold_minutes
        return None


# -- matematika -------------------------------------------------------------


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def parse_klines(raw: Any) -> list[dict[str, Decimal]]:
    """A Bitunix válaszból ``[{open, high, low, close, time}, ...]`` lista.

    Idő szerint növekvő sorrendbe rendezi (a Bitunix néha csökkenőt ad).
    """
    data = raw.get("data", raw) if isinstance(raw, dict) else raw
    if not isinstance(data, list):
        return []
    out: list[dict[str, Decimal]] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        o = _to_decimal(row.get("open"))
        h = _to_decimal(row.get("high"))
        low = _to_decimal(row.get("low"))
        c = _to_decimal(row.get("close"))
        if o is None or h is None or low is None or c is None or c <= 0:
            continue
        ts = row.get("time") or row.get("ts") or 0
        out.append({"open": o, "high": h, "low": low, "close": c, "time": Decimal(ts)})
    out.sort(key=lambda r: r["time"])
    return out


def compute_atr_pct(klines: list[dict[str, Decimal]]) -> Decimal | None:
    """ATR a záróár százalékában (Wilder True Range egyszerű átlagolva).

    Visszaad ``None``-t, ha túl kevés gyertya van.
    """
    if len(klines) < 2:
        return None
    trs: list[Decimal] = []
    for i in range(1, len(klines)):
        prev_close = klines[i - 1]["close"]
        high = klines[i]["high"]
        low = klines[i]["low"]
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )
        close = klines[i]["close"]
        if close > 0:
            trs.append((tr / close) * Decimal(100))
    if not trs:
        return None
    return sum(trs, Decimal(0)) / Decimal(len(trs))


def apply_hold_window_to_symbol_calibration(
    calibration: SymbolCalibration,
    klines_raw: Any,
    *,
    choppiness_max: Decimal,
    cooldown_minutes: int,
    hold_params: HoldWindowParams,
    hold_klines: list[dict[str, Decimal]] | None = None,
    hold_sim_interval: str | None = None,
) -> None:
    """Hold-window rács a szimbólum kline-jain (WF szekvencia + medián×0.5 TP/SL)."""
    if not hold_params.enabled:
        return
    from app.services.coin_analyze import _build_walk_forward_sequence_core

    klines = parse_klines(klines_raw)
    if len(klines) < 20:
        return
    seq = _build_walk_forward_sequence_core(
        klines,
        choppiness_max=choppiness_max,
        tp_median_multiplier=Decimal("0.5"),
        sl_median_multiplier=Decimal("0.5"),
        cooldown_minutes=cooldown_minutes,
        clip_variation_tpsl_bounds=True,
    )
    hw = optimize_hold_window_for_sequence(
        klines,
        seq,
        params=hold_params,
        hold_klines=hold_klines,
        hold_sim_interval=hold_sim_interval,
    )
    best = hw.get("best_hold_minutes")
    if best is not None:
        calibration.best_hold_minutes = int(best)
    rate_s = hw.get("best_good_rate_pct")
    if rate_s is not None:
        calibration.hold_good_rate_pct = Decimal(str(rate_s))


def compute_calibration_for_symbol(
    symbol: str,
    klines_raw: Any,
    *,
    tp_atr_mult: Decimal,
    sl_atr_mult: Decimal,
    abs_change_24h_pct: Decimal,
) -> SymbolCalibration | None:
    """Egy szimbólum kalibrációja a kapott kline-okból.

    TP/SL move %% = ``ATR_pct ×`` szorzók, **padló/plafon nélkül** (nyers ATR
    alapú cél).
    """
    klines = parse_klines(klines_raw)
    atr_pct = compute_atr_pct(klines)
    if atr_pct is None or atr_pct <= 0:
        return None
    tp_pct = atr_pct * tp_atr_mult
    sl_pct = atr_pct * sl_atr_mult
    return SymbolCalibration(
        symbol=symbol,
        tp_move_pct=tp_pct,
        sl_move_pct=sl_pct,
        atr_pct=atr_pct,
        samples=len(klines),
        last_close=klines[-1]["close"],
        abs_change_24h_pct=abs_change_24h_pct,
    )


def rank_top_symbols(tickers_raw: Any, *, top_n: int) -> list[tuple[str, Decimal]]:
    """A top N szimbólum ``(symbol, abs_change_pct)`` |24h %| csökkenőben."""
    if isinstance(tickers_raw, dict):
        items_raw = tickers_raw.get("data", tickers_raw)
    else:
        items_raw = tickers_raw
    if not isinstance(items_raw, list):
        return []
    out: list[tuple[str, Decimal]] = []
    for item in items_raw:
        if not isinstance(item, dict):
            continue
        symbol = item.get("symbol")
        last = _to_decimal(item.get("lastPrice") or item.get("last"))
        open_p = _to_decimal(item.get("open"))
        if not symbol or last is None or open_p is None or open_p == 0:
            continue
        change_pct = abs((last - open_p) / open_p) * Decimal(100)
        out.append((str(symbol), change_pct))
    out.sort(key=lambda t: t[1], reverse=True)
    return out[:top_n]


# -- service ---------------------------------------------------------------


class CalibrationService:
    """Top mozgók 7 napos backtest kalibrációja (:15 belépés, fix TP/SL rács)."""

    def __init__(
        self,
        client: BitunixClient,
        *,
        calibration_id: int,
        lookback_minutes: int = 120,
        top_n: int = 20,
        candidates_target: int = 10,
        tp_atr_mult: Decimal = Decimal("3.0"),
        sl_atr_mult: Decimal = Decimal("1.5"),
        kline_interval: str = "15m",
        wf_choppiness_max: Decimal = Decimal("1.72"),
    ) -> None:
        self._client = client
        self._calibration_id = calibration_id
        self._lookback_minutes = lookback_minutes
        self._top_n = top_n
        self._candidates_target = max(0, int(candidates_target))
        self._tp_atr_mult = tp_atr_mult
        self._sl_atr_mult = sl_atr_mult
        self._interval = kline_interval
        self._wf_choppiness_max = wf_choppiness_max

    async def run(self) -> CalibrationResult:
        """Top coinok végigjárása, amíg meg nem van a cél számú jelölt."""
        from app.services.candidate_backtest import (
            QualifiedCandidate,
            evaluate_symbol_variations,
        )
        from app.services.kline_fetch import fetch_lookback_klines

        result = CalibrationResult(
            started_at=datetime.now(UTC),
            lookback_minutes=self._lookback_minutes,
            top_n=self._top_n,
            candidates_target=self._candidates_target,
            tp_atr_mult=self._tp_atr_mult,
            sl_atr_mult=self._sl_atr_mult,
            mode="candidate_backtest",
        )

        if self._candidates_target <= 0:
            result.finished_at = datetime.now(UTC)
            return result

        tickers_raw = await self._client.get_all_tickers()
        top_symbols = rank_top_symbols(tickers_raw, top_n=self._top_n)
        end_ms = int(datetime.now(UTC).timestamp() * 1000)
        qualified: list[QualifiedCandidate] = []

        async def _flush_symbol_run(draft: SymbolRunDraft) -> None:
            await persist_symbol_run_committed(
                self._calibration_id,
                draft,
                scanned_symbols=result.scanned_symbols,
                candidates_found=len(qualified),
                candidates_target=self._candidates_target,
                top_n=self._top_n,
            )

        for rank, (symbol, abs_change) in enumerate(top_symbols, start=1):
            result.scanned_symbols += 1
            try:
                klines = await fetch_lookback_klines(
                    self._client,
                    symbol,
                    lookback_minutes=self._lookback_minutes,
                    interval=self._interval,
                    bar_minutes=15,
                    end_time_ms=end_ms,
                )
            except (BitunixAPIError, BitunixSignatureError) as exc:
                draft = draft_from_fetch_failure(
                    symbol=symbol,
                    scan_rank=rank,
                    abs_change_24h_pct=abs_change,
                    error=str(exc),
                )
                result.symbol_run_drafts.append(draft)
                result.failed_symbols.append(
                    {"symbol": symbol, "reason": "fetch_failed", "error": str(exc)}
                )
                await _flush_symbol_run(draft)
                continue

            eval_out = evaluate_symbol_variations(
                klines, choppiness_max=self._wf_choppiness_max
            )
            best = eval_out.get("best_variation")
            meets_backtest = bool(eval_out.get("ok") and best is not None)
            take_as_candidate = (
                meets_backtest and len(qualified) < self._candidates_target
            )

            draft = draft_from_evaluation(
                symbol=symbol,
                scan_rank=rank,
                abs_change_24h_pct=abs_change,
                kline_samples=len(klines),
                eval_out=eval_out,
                is_selected_candidate=take_as_candidate,
            )
            result.symbol_run_drafts.append(draft)

            if not meets_backtest:
                result.failed_symbols.append(
                    {
                        "symbol": symbol,
                        "reason": eval_out.get("reason", "not_qualified"),
                        "variations": eval_out.get("variations"),
                    }
                )
                await _flush_symbol_run(draft)
                continue

            if not take_as_candidate:
                await _flush_symbol_run(draft)
                continue

            tp_roi = Decimal(str(best["tp_roi_pct"]))
            sl_roi = Decimal(str(best["sl_roi_pct"]))
            win_rate = Decimal(str(best["resolved_tp_win_rate_pct"]))
            tp_move, sl_move = implied_price_move_pct_from_roi(
                leverage=20,
                tp_roi_pct=tp_roi,
                sl_roi_pct=sl_roi,
            )
            last_close = klines[-1]["close"] if klines else Decimal(0)
            sym_cal = SymbolCalibration(
                symbol=symbol,
                tp_move_pct=tp_move,
                sl_move_pct=sl_move,
                atr_pct=Decimal(0),
                samples=len(klines),
                last_close=last_close,
                abs_change_24h_pct=abs_change,
                tp_roi_pct=tp_roi,
                sl_roi_pct=sl_roi,
                backtest_win_rate_pct=win_rate,
                variation_label=str(best.get("label", "")),
                backtest_variations=list(eval_out.get("variations") or []),
            )
            result.per_symbol[symbol] = sym_cal
            cand = QualifiedCandidate(
                symbol=symbol,
                rank=rank,
                abs_change_24h_pct=abs_change,
                tp_roi_pct=tp_roi,
                sl_roi_pct=sl_roi,
                win_rate_pct=win_rate,
                variation_label=str(best.get("label", "")),
                trade_count=int((best.get("summary") or {}).get("total_trades", 0)),
                variations=list(eval_out.get("variations") or []),
            )
            qualified.append(cand)
            await _flush_symbol_run(draft)

        result.candidates_found = len(qualified)
        result.qualified_candidates = [c.to_summary_dict() for c in qualified]
        if result.per_symbol:
            tp_values = [s.tp_move_pct for s in result.per_symbol.values()]
            sl_values = [s.sl_move_pct for s in result.per_symbol.values()]
            result.global_tp_move_pct = Decimal(str(median(tp_values)))
            result.global_sl_move_pct = Decimal(str(median(sl_values)))
        result.finished_at = datetime.now(UTC)
        return result


def load_result_from_summary(summary: dict[str, Any]) -> CalibrationResult:
    """``TpSlCalibration.summary`` → in-memory ``CalibrationResult``."""
    result = CalibrationResult(
        started_at=datetime.now(UTC),
        lookback_minutes=int(summary.get("lookback_minutes", 120)),
        top_n=int(summary.get("top_n", 20)),
        tp_atr_mult=Decimal(str(summary.get("tp_atr_mult", "3.0"))),
        sl_atr_mult=Decimal(str(summary.get("sl_atr_mult", "1.5"))),
        mode=str(summary.get("mode", "candidate_backtest")),
        candidates_target=int(summary.get("candidates_target", 0)),
        candidates_found=int(summary.get("candidates_found", 0)),
        scanned_symbols=int(summary.get("scanned_symbols", 0)),
        qualified_candidates=list(summary.get("qualified_candidates") or []),
    )
    global_data = summary.get("global") or {}
    gtp = global_data.get("tp_move_pct")
    gsl = global_data.get("sl_move_pct")
    if gtp is not None:
        result.global_tp_move_pct = Decimal(str(gtp))
    if gsl is not None:
        result.global_sl_move_pct = Decimal(str(gsl))
    per_symbol = summary.get("per_symbol") or {}
    for sym, payload in per_symbol.items():
        try:
            bh = payload.get("best_hold_minutes")
            hgr = payload.get("hold_good_rate_pct")
            tpr = payload.get("tp_roi_pct")
            slr = payload.get("sl_roi_pct")
            bwr = payload.get("backtest_win_rate_pct")
            result.per_symbol[sym] = SymbolCalibration(
                symbol=sym,
                tp_move_pct=Decimal(str(payload["tp_move_pct"])),
                sl_move_pct=Decimal(str(payload["sl_move_pct"])),
                atr_pct=Decimal(str(payload.get("atr_pct", "0"))),
                samples=int(payload.get("samples", 0)),
                last_close=Decimal(str(payload.get("last_close", "0"))),
                abs_change_24h_pct=Decimal(
                    str(payload.get("abs_change_24h_pct", "0"))
                ),
                best_hold_minutes=int(bh) if bh is not None else None,
                hold_good_rate_pct=(
                    Decimal(str(hgr)) if hgr is not None else None
                ),
                tp_roi_pct=Decimal(str(tpr)) if tpr is not None else None,
                sl_roi_pct=Decimal(str(slr)) if slr is not None else None,
                backtest_win_rate_pct=(
                    Decimal(str(bwr)) if bwr is not None else None
                ),
                variation_label=payload.get("variation_label"),
                backtest_variations=payload.get("backtest_variations"),
            )
        except (KeyError, TypeError, ValueError):
            continue
    return result
