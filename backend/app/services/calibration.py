"""TP/SL automatikus belövő (kalibrációs) service.

Algoritmus röviden:
1. Lekérjük az összes 24h tickert és kiválasztjuk a **top N** szimbólumot
   ``|24h % változás|`` alapján (konzisztens a top_movers stratégiával).
2. Mindegyikre 2 órányi 1-perces kline-t (=120 gyertya) kérünk le.
3. Kiszámoljuk a True Range-et (TR) és az ATR-t a closing ár %-ában.
   Az ATR a recent realized volatility robusztus, klasszikus mértéke.
4. TP target = ``ATR_pct × tp_atr_multiplier`` (alap: 3.0)
   SL target = ``ATR_pct × sl_atr_multiplier`` (alap: 1.5)
   → R:R ~ 2:1 (matematikailag pozitív várt érték még 40%-os hit rate-nél is).
5. Tároljuk per-symbol és számolunk globális mediánt (fallback olyan
   szimbólumokra, amiket a top_movers stratégia idő közben kiválaszt,
   de nem volt a top20-ban a kalibrációkor).

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


def compute_calibration_for_symbol(
    symbol: str,
    klines_raw: Any,
    *,
    tp_atr_mult: Decimal,
    sl_atr_mult: Decimal,
    abs_change_24h_pct: Decimal,
    min_tp_move_pct: Decimal,
    min_sl_move_pct: Decimal,
    max_tp_move_pct: Decimal,
    max_sl_move_pct: Decimal,
) -> SymbolCalibration | None:
    """Egy szimbólum kalibrációja a kapott kline-okból.

    A targetek a ``min`` / ``max`` korlátok közé szorítva, hogy se nullszerű
    se eszméletlenül széles TP/SL ne keletkezzen.
    """
    klines = parse_klines(klines_raw)
    atr_pct = compute_atr_pct(klines)
    if atr_pct is None or atr_pct <= 0:
        return None
    raw_tp = atr_pct * tp_atr_mult
    raw_sl = atr_pct * sl_atr_mult
    tp_pct = max(min(raw_tp, max_tp_move_pct), min_tp_move_pct)
    sl_pct = max(min(raw_sl, max_sl_move_pct), min_sl_move_pct)
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
        min_tp_move_pct: Decimal = Decimal("0.20"),
        min_sl_move_pct: Decimal = Decimal("0.10"),
        max_tp_move_pct: Decimal = Decimal("10.0"),
        max_sl_move_pct: Decimal = Decimal("5.0"),
        kline_interval: str = "1m",
    ) -> None:
        self._client = client
        self._lookback_minutes = lookback_minutes
        self._top_n = top_n
        self._tp_atr_mult = tp_atr_mult
        self._sl_atr_mult = sl_atr_mult
        self._min_tp = min_tp_move_pct
        self._min_sl = min_sl_move_pct
        self._max_tp = max_tp_move_pct
        self._max_sl = max_sl_move_pct
        self._interval = kline_interval

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
                klines_raw = await self._client.get_klines(
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
                min_tp_move_pct=self._min_tp,
                min_sl_move_pct=self._min_sl,
                max_tp_move_pct=self._max_tp,
                max_sl_move_pct=self._max_sl,
            )
            if calibration is None:
                result.failed_symbols.append(
                    {"symbol": symbol, "reason": "insufficient_kline_data"}
                )
                continue
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
            )
        except (KeyError, TypeError, ValueError):
            continue
    return result
