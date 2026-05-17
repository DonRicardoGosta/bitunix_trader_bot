"""TP/SL automatikus belövő (kalibrációs) service.

Algoritmus röviden:
1. Lekérjük az összes 24h tickert és kiválasztjuk a **top N** szimbólumot
   ``|24h % változás|`` alapján (konzisztens a top_signal_entries rangsorolással).
2. Mindegyikre 2 órányi 1-perces kline-t (=120 gyertya) kérünk le.
3. Kiszámoljuk a True Range-et (TR) és az ATR-t a closing ár %-ában.
   Az ATR a recent realized volatility robusztus, klasszikus mértéke.
4. TP target = ``ATR_pct × tp_atr_multiplier`` (alap: 3.0)
   SL target = ``ATR_pct × sl_atr_multiplier`` (alap: 1.5)
   → R:R ~ 2:1 (matematikailag pozitív várt érték még 40%-os hit rate-nél is).
5. Tároljuk per-symbol és számolunk globális mediánt (fallback olyan
   szimbólumokra, amiket a stratégia idő közben kiválaszt,
   de nem volt a top-N-ben a kalibrációkor). A stratégia a **per-symbol
   kiszámolt TP/SL move %%**-et használja; ha nincs ilyen rekord, a **globális
   mediánt** (``CalibrationResult.lookup``).

Megjegyzés: az output **price move %** (leverage-független). A stratégia
ebből számol konkrét TP/SL árat: ``tp_price = entry × (1 + tp_pct/100)``
LONG-nál. Ez tisztább, mint ROI % alapon dolgozni, és nem érzékeny a
leverage változására két futtatás között.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from statistics import median
from typing import Any

from app.bitunix.client import BitunixClient
from app.bitunix.exceptions import BitunixAPIError, BitunixSignatureError
from app.services.hold_window import HoldWindowParams, optimize_hold_window_for_sequence


@dataclass
class SymbolCalibration:
    """Egy szimbólum kalibrációs eredménye."""

    symbol: str
    tp_move_pct: Decimal
    sl_move_pct: Decimal
    atr_pct: Decimal
    samples: int
    last_close: Decimal
    abs_change_24h_pct: Decimal
    best_hold_minutes: int | None = None
    hold_good_rate_pct: Decimal | None = None


@dataclass
class CalibrationResult:
    """Egy kalibrációs lefutás teljes eredménye."""

    started_at: datetime
    finished_at: datetime | None = None
    per_symbol: dict[str, SymbolCalibration] = field(default_factory=dict)
    global_tp_move_pct: Decimal | None = None
    global_sl_move_pct: Decimal | None = None
    failed_symbols: list[dict[str, Any]] = field(default_factory=list)
    lookback_minutes: int = 120
    top_n: int = 20
    tp_atr_mult: Decimal = Decimal("3.0")
    sl_atr_mult: Decimal = Decimal("1.5")

    def to_dict(self) -> dict[str, Any]:
        return {
            "lookback_minutes": self.lookback_minutes,
            "top_n": self.top_n,
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
                }
                for sym, s in self.per_symbol.items()
            },
            "failed_symbols": self.failed_symbols,
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
    """Top N szimbólum kalibrációja a Bitunix kline adataiból."""

    def __init__(
        self,
        client: BitunixClient,
        *,
        lookback_minutes: int = 120,
        top_n: int = 20,
        tp_atr_mult: Decimal = Decimal("3.0"),
        sl_atr_mult: Decimal = Decimal("1.5"),
        kline_interval: str = "1m",
        hold_params: HoldWindowParams | None = None,
        wf_choppiness_max: Decimal = Decimal("1.72"),
        wf_cooldown_minutes: int = 60,
    ) -> None:
        self._client = client
        self._lookback_minutes = lookback_minutes
        self._top_n = top_n
        self._tp_atr_mult = tp_atr_mult
        self._sl_atr_mult = sl_atr_mult
        self._interval = kline_interval
        self._hold_params = hold_params or HoldWindowParams()
        self._wf_choppiness_max = wf_choppiness_max
        self._wf_cooldown_minutes = wf_cooldown_minutes

    async def run(self) -> CalibrationResult:
        """A teljes kalibrációs ciklust lefuttatja."""
        result = CalibrationResult(
            started_at=datetime.now(UTC),
            lookback_minutes=self._lookback_minutes,
            top_n=self._top_n,
            tp_atr_mult=self._tp_atr_mult,
            sl_atr_mult=self._sl_atr_mult,
        )

        tickers_raw = await self._client.get_all_tickers()
        top_symbols = rank_top_symbols(tickers_raw, top_n=self._top_n)

        # kline lekérés visszafelé számolt időablakkal (utolsó 2 óra)
        end_ms = int(datetime.now(UTC).timestamp() * 1000)
        start_ms = end_ms - self._lookback_minutes * 60 * 1000
        # 1m gyertyák → max 200 a Bitunix limit, 120 fér el bőven
        kline_limit = min(200, self._lookback_minutes + 5)

        for symbol, abs_change in top_symbols:
            try:
                from app.services.kline_fetch import get_klines_rate_limited

                klines_raw = await get_klines_rate_limited(
                    self._client,
                    symbol,
                    interval=self._interval,
                    limit=kline_limit,
                    start_time_ms=start_ms,
                    end_time_ms=end_ms,
                )
            except (BitunixAPIError, BitunixSignatureError) as exc:
                result.failed_symbols.append(
                    {"symbol": symbol, "reason": "fetch_failed", "error": str(exc)}
                )
                continue

            calibration = compute_calibration_for_symbol(
                symbol,
                klines_raw,
                tp_atr_mult=self._tp_atr_mult,
                sl_atr_mult=self._sl_atr_mult,
                abs_change_24h_pct=abs_change,
            )
            if calibration is None:
                result.failed_symbols.append(
                    {"symbol": symbol, "reason": "insufficient_kline_data"}
                )
                continue
            hold_klines = None
            hold_sim_interval: str | None = None
            if self._hold_params.enabled:
                from app.services.kline_fetch import (
                    HOLD_SIM_INTERVAL,
                    fetch_hold_simulation_klines,
                )

                hold_sim_interval = HOLD_SIM_INTERVAL
                hold_klines = await fetch_hold_simulation_klines(
                    self._client,
                    symbol,
                    lookback_minutes=self._lookback_minutes,
                    hold_max_minutes=self._hold_params.max_minutes,
                    end_time_ms=end_ms,
                )
            apply_hold_window_to_symbol_calibration(
                calibration,
                klines_raw,
                choppiness_max=self._wf_choppiness_max,
                cooldown_minutes=self._wf_cooldown_minutes,
                hold_params=self._hold_params,
                hold_klines=hold_klines,
                hold_sim_interval=hold_sim_interval,
            )
            result.per_symbol[symbol] = calibration

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
            )
        except (KeyError, TypeError, ValueError):
            continue
    return result
