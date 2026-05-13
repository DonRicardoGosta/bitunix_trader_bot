"""Top Movers stratégia.

Specifikáció:

* Kérdezzük le a Bitunix futures piac **összes szimbólumát** 24h tickerekkel.
* Rangsoroljuk őket az **abszolút** 24h % változás szerint csökkenő sorrendben.
* Vegyük a **top N** abszolút mozgást (N = ``STRATEGY_TOP_MOVERS_SCAN_LIMIT``),
  és a Bitunix **nyitott pozíciók** alapján töltjük fel a
  ``STRATEGY_TOP_MOVERS_COUNT`` (alap 3) „slotot”: ha egy pozíció TP/SL-lel
  lezárult, a következő futáskor a rangsor következő szimbóluma kerül szóba.
* Minden szimbólumra:
    * **Cooldown:** ha 4 órán belül már nyitottunk ugyanennek a stratégiának
      ezzel a szimbólummal, kihagyjuk.
    * **Leverage:** lekérdezzük a ``trading_pairs``-ből a ``maxLeverage``-t,
      és beállítjuk az adott szimbólumra (``change_leverage`` REST hívás).
    * **Margin:** a futures USDT egyenleg 1%-a, de minimum 0.25 USDT.
    * **Irány:** konfigurálható (``trend`` / ``momentum_breakout`` /
      ``mean_revert``). Az alapérték a ``momentum_breakout`` – az ár 24h
      range-en belüli helyzetét is figyelembe veszi és kihagyja a kétértelmű
      eseteket. Lásd ``decide_direction``.
    * **TP/SL kalibráció:** a szimbólum **saját** kalibrált move %% (ATR×szorzó),
      ha van a legutóbbi kalibrációban; különben a **globális TP/SL medián**.
      Ha egyik sincs, ROI fallback (``STRATEGY_TP_ROI_PCT`` /
      ``STRATEGY_SL_ROI_PCT``); lásd ``app/services/tpsl.py``.
    * Piaci rendelés a Bitunix ``/futures/trade/place_order``-en, beépített
      ``tpPrice`` és ``slPrice`` paraméterekkel.
    * Ha a tőzsde elutasítja a rendelést (pl. min. mennyiség), a stratégia
      **nem áll le**: naplózza, kihagyja az adott szimbólumot, és megy tovább
      a következő top moverre.

Megjegyzés: a Bitunix dokumentáció ``lastPrice``, ``open``, ``high``, ``low``
mezőket ad a 24h tickerben → a változás % így számolt:
``(last - open) / open × 100``, a range pozíció: ``(last - low) / (high - low)``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import sqlalchemy as sa

from app.bitunix.exceptions import BitunixAPIError, BitunixSignatureError
from app.db import audit
from app.db.models import AuditLevel, Order
from app.schemas.trading import OrderRequest
from app.services.calibration_runner import get_active_calibration_result
from app.services.risk import compute_margin, compute_quantity
from app.services.strategy.base import Strategy, StrategyContext, StrategyResult
from app.services.tpsl import (
    compute_tp_sl_prices_from_move_pct,
    implied_price_move_pct_from_roi,
    is_risky_sl_roi,
)
from app.services.trading import TradingService


class TopMoversStrategy(Strategy):
    """Top-N abszolút 24h mozgás momentum stratégia."""

    name = "top_movers"

    async def run(self, ctx: StrategyContext) -> StrategyResult:
        result = StrategyResult()
        settings = ctx.settings

        if not settings.strategy_top_movers_enabled:
            await audit.record(
                ctx.session,
                "strategy.skipped",
                level=AuditLevel.INFO,
                message="top_movers ki van kapcsolva (config).",
                strategy_name=self.name,
            )
            result.details["reason"] = "disabled"
            return result

        # GATE: kell-e friss kalibráció?
        calibration = await get_active_calibration_result(ctx.session)
        if settings.require_calibration_for_trading and calibration is None:
            await audit.record(
                ctx.session,
                "strategy.top_movers.calibration_missing",
                level=AuditLevel.WARNING,
                message=(
                    "Nincs friss TP/SL kalibráció – a stratégia kihagyja "
                    "a kereskedést, amíg a calibration runner lefut."
                ),
                strategy_name=self.name,
            )
            result.details["reason"] = "calibration_missing"
            return result

        target_slots = max(1, int(settings.strategy_top_movers_count))
        scan_limit = max(
            target_slots,
            min(int(settings.strategy_top_movers_scan_limit), 200),
        )
        cooldown_minutes = int(settings.strategy_top_movers_cooldown_minutes)
        pct_of_balance = Decimal(settings.strategy_margin_pct_of_balance)
        min_margin = Decimal(settings.strategy_min_margin_usdt)

        # 1) tickers + 2) trading pairs (max leverage + precíziók) párhuzamos lekérése
        tickers_raw = await ctx.client.get_all_tickers()
        pairs_raw = await ctx.client.get_trading_pairs()

        movers = _rank_top_movers(tickers_raw, top_n=scan_limit)
        pair_meta = _index_trading_pairs(pairs_raw)

        try:
            pos_raw = await ctx.client.get_positions()
            open_syms = _parse_open_position_symbols(pos_raw)
        except (BitunixAPIError, BitunixSignatureError) as exc:
            await audit.record(
                ctx.session,
                "strategy.top_movers.positions_error",
                level=AuditLevel.WARNING,
                message=f"Pozíciók lekérése sikertelen (slot számolás üres halmazzal): {exc}",
                payload={"error": str(exc)},
                strategy_name=self.name,
            )
            open_syms = set()
        except Exception as exc:  # noqa: BLE001
            await audit.record(
                ctx.session,
                "strategy.top_movers.positions_error",
                level=AuditLevel.WARNING,
                message=f"Pozíciók parse/hálózat hiba: {exc}",
                payload={"error": str(exc)},
                strategy_name=self.name,
            )
            open_syms = set()

        total_open = len(open_syms)
        need = max(0, target_slots - total_open)

        await audit.record(
            ctx.session,
            "strategy.top_movers.ranked",
            level=AuditLevel.INFO,
            message=(
                f"Top {len(movers)} / scan={scan_limit}, "
                f"nyitott szimbólumok: {total_open}, kitöltendő slot: {need}."
            ),
            payload={
                "target_slots": target_slots,
                "scan_limit": scan_limit,
                "open_symbols_sample": sorted(open_syms)[:40],
                "total_open_positions": total_open,
                "slots_to_fill": need,
                "candidates": [
                    {"symbol": m.symbol, "change_pct": str(m.change_pct), "last": str(m.last_price)}
                    for m in movers[:25]
                ],
            },
            strategy_name=self.name,
        )

        # 3) Futures egyenleg → margin
        try:
            account_raw = await ctx.client.get_account(settings.bitunix_margin_coin)
        except (BitunixAPIError, BitunixSignatureError) as exc:
            await audit.record(
                ctx.session,
                "strategy.top_movers.balance_error",
                level=AuditLevel.ERROR,
                message=str(exc),
                strategy_name=self.name,
            )
            raise

        available_balance = _extract_available_usdt(account_raw)
        margin_usdt = compute_margin(
            available_balance,
            pct_of_balance=pct_of_balance,
            minimum_usdt=min_margin,
        )
        result.details["available_balance_usdt"] = str(available_balance)
        result.details["margin_per_position_usdt"] = str(margin_usdt)

        await audit.record(
            ctx.session,
            "strategy.top_movers.margin_computed",
            level=AuditLevel.INFO,
            message=(
                f"Egyenleg: {available_balance} USDT → margin/pozíció: {margin_usdt} USDT "
                f"(1% min {min_margin})."
            ),
            payload={
                "available_balance": str(available_balance),
                "margin_per_position": str(margin_usdt),
                "pct_of_balance": str(pct_of_balance),
                "min_margin": str(min_margin),
            },
            strategy_name=self.name,
        )

        cooldown_until_after = datetime.now(UTC) - timedelta(minutes=cooldown_minutes)
        trading_service = TradingService(ctx.client, ctx.session)
        direction_mode = settings.strategy_top_movers_direction_mode
        range_threshold = Decimal(settings.strategy_top_movers_range_threshold)
        tp_roi = Decimal(settings.strategy_tp_roi_pct)
        sl_roi = Decimal(settings.strategy_sl_roi_pct)
        result.details["direction_mode"] = direction_mode
        result.details["calibration_used"] = calibration is not None
        if calibration is not None:
            result.details["calibration_global"] = {
                "tp_move_pct": (
                    str(calibration.global_tp_move_pct)
                    if calibration.global_tp_move_pct is not None
                    else None
                ),
                "sl_move_pct": (
                    str(calibration.global_sl_move_pct)
                    if calibration.global_sl_move_pct is not None
                    else None
                ),
                "symbol_count": len(calibration.per_symbol),
            }
        else:
            result.details["tp_roi_pct"] = str(tp_roi)
            result.details["sl_roi_pct"] = str(sl_roi)

        if calibration is None and is_risky_sl_roi(sl_roi):
            await audit.record(
                ctx.session,
                "strategy.top_movers.risky_sl_warning",
                level=AuditLevel.WARNING,
                message=(
                    f"SL ROI {sl_roi}% magas (likvidáció-közeli). "
                    "Megfontolandó 50-75% közé csökkenteni, vagy hagyatkozni "
                    "a kalibrációra."
                ),
                payload={"sl_roi_pct": str(sl_roi)},
                strategy_name=self.name,
            )

        result.details["position_slots"] = {
            "target": target_slots,
            "scan_limit": scan_limit,
            "total_open_positions": total_open,
            "slots_to_fill": need,
        }

        placed_run = 0
        if need > 0:
            for mover in movers:
                if placed_run >= need:
                    break
                if mover.symbol in open_syms:
                    result.skipped.append(
                        {
                            "symbol": mover.symbol,
                            "placed": False,
                            "reason": "position_already_open",
                            "change_pct": str(mover.change_pct),
                        }
                    )
                    continue
                decision = await self._maybe_place(
                    ctx,
                    mover=mover,
                    pair_meta=pair_meta,
                    margin_usdt=margin_usdt,
                    cooldown_after=cooldown_until_after,
                    trading_service=trading_service,
                    direction_mode=direction_mode,
                    range_threshold=range_threshold,
                    tp_roi=tp_roi,
                    sl_roi=sl_roi,
                    stop_type=settings.strategy_tpsl_stop_type,
                    calibration=calibration,
                )
                if decision.get("placed"):
                    placed_run += 1
                    open_syms.add(mover.symbol)
                    result.placed_orders.append(decision)
                else:
                    result.skipped.append(decision)
        else:
            await audit.record(
                ctx.session,
                "strategy.top_movers.slots_full",
                level=AuditLevel.INFO,
                message=(
                    f"Nincs új belépés: {total_open} nyitott pozíció ≥ "
                    f"{target_slots} slot cél."
                ),
                payload={
                    "target_slots": target_slots,
                    "total_open_positions": total_open,
                },
                strategy_name=self.name,
            )

        result.details["position_slots"]["placed_this_run"] = placed_run

        return result

    async def _maybe_place(
        self,
        ctx: StrategyContext,
        *,
        mover: _Mover,
        pair_meta: dict[str, _PairMeta],
        margin_usdt: Decimal,
        cooldown_after: datetime,
        trading_service: TradingService,
        direction_mode: str,
        range_threshold: Decimal,
        tp_roi: Decimal,
        sl_roi: Decimal,
        stop_type: str,
        calibration: Any | None = None,
    ) -> dict[str, Any]:
        """Egy szimbólumra a teljes döntéslánc + végrehajtás."""
        symbol = mover.symbol
        out: dict[str, Any] = {
            "symbol": symbol,
            "change_pct": str(mover.change_pct),
            "range_position": (
                str(mover.range_position) if mover.range_position is not None else None
            ),
        }

        # 1) cooldown
        last = await self._last_order_at(ctx, symbol)
        if last and last > cooldown_after:
            out["placed"] = False
            out["reason"] = "cooldown"
            out["last_order_at"] = last.isoformat()
            await audit.record(
                ctx.session,
                "strategy.top_movers.cooldown_skip",
                level=AuditLevel.INFO,
                message=f"{symbol} cooldownban (utolsó: {last.isoformat()}).",
                payload=out,
                strategy_name=self.name,
            )
            return out

        # 2) trading pair meta
        meta = pair_meta.get(symbol)
        if meta is None:
            out["placed"] = False
            out["reason"] = "no_trading_pair_metadata"
            await audit.record(
                ctx.session,
                "strategy.top_movers.no_metadata",
                level=AuditLevel.WARNING,
                message=f"{symbol} nem található a trading_pairs listában.",
                payload=out,
                strategy_name=self.name,
            )
            return out

        # 3) irány eldöntése (skip ha kétértelmű momentum_breakout módban)
        side, reason = decide_direction(
            mover, mode=direction_mode, range_threshold=range_threshold
        )
        out["direction_reason"] = reason
        if side is None:
            out["placed"] = False
            out["reason"] = "direction_skip"
            await audit.record(
                ctx.session,
                "strategy.top_movers.direction_skip",
                level=AuditLevel.INFO,
                message=f"{symbol} kihagyva: {reason}",
                payload=out,
                strategy_name=self.name,
            )
            return out

        leverage = max(1, int(meta.max_leverage))

        # 4) max leverage beállítása a Bitunixon
        try:
            lev_response = await ctx.client.change_leverage(
                symbol=symbol,
                leverage=leverage,
                margin_coin=ctx.settings.bitunix_margin_coin,
            )
        except (BitunixAPIError, BitunixSignatureError) as exc:
            out["placed"] = False
            out["reason"] = "change_leverage_failed"
            out["error"] = str(exc)
            await audit.record(
                ctx.session,
                "strategy.top_movers.leverage_error",
                level=AuditLevel.ERROR,
                message=f"Leverage beállítás hiba {symbol}: {exc}",
                payload=out,
                strategy_name=self.name,
            )
            return out

        await audit.record(
            ctx.session,
            "strategy.top_movers.leverage_set",
            level=AuditLevel.INFO,
            message=f"{symbol} leverage → {leverage}x",
            payload={"symbol": symbol, "leverage": leverage, "response": lev_response},
            strategy_name=self.name,
        )

        # 5) mennyiség
        qty = compute_quantity(
            margin_usdt=margin_usdt,
            leverage=leverage,
            price=mover.last_price,
            base_precision=meta.base_precision,
        )
        if qty <= 0:
            out["placed"] = False
            out["reason"] = "quantity_rounded_to_zero"
            out["margin_usdt"] = str(margin_usdt)
            out["price"] = str(mover.last_price)
            out["leverage"] = leverage
            await audit.record(
                ctx.session,
                "strategy.top_movers.qty_zero",
                level=AuditLevel.WARNING,
                message=(
                    f"{symbol} mennyiség 0-ra kerekedett "
                    f"(margin={margin_usdt}, lev={leverage}, price={mover.last_price})."
                ),
                payload=out,
                strategy_name=self.name,
            )
            return out

        # 6) TP / SL — kalibrált move: per-symbol, különben globál medián; ha
        # nincs adat, ROI fallback (nincs padló/plafon).
        tp_source = "roi_fallback"
        try:
            if calibration is not None:
                moves = calibration.lookup(symbol)
                if moves is not None:
                    tp_move_pct, sl_move_pct = moves
                    if symbol in calibration.per_symbol:
                        tp_source = "calibration_symbol"
                    else:
                        tp_source = "calibration_global"
                else:
                    tp_move_pct, sl_move_pct = implied_price_move_pct_from_roi(
                        leverage=leverage,
                        tp_roi_pct=tp_roi,
                        sl_roi_pct=sl_roi,
                    )
            else:
                tp_move_pct, sl_move_pct = implied_price_move_pct_from_roi(
                    leverage=leverage,
                    tp_roi_pct=tp_roi,
                    sl_roi_pct=sl_roi,
                )
            tp_price, sl_price = compute_tp_sl_prices_from_move_pct(
                entry_price=mover.last_price,
                side=side,
                tp_move_pct=tp_move_pct,
                sl_move_pct=sl_move_pct,
                price_precision=meta.price_precision,
            )
            out["tp_move_pct"] = str(tp_move_pct)
            out["sl_move_pct"] = str(sl_move_pct)
        except ValueError as exc:
            out["placed"] = False
            out["reason"] = "tpsl_computation_failed"
            out["error"] = str(exc)
            await audit.record(
                ctx.session,
                "strategy.top_movers.tpsl_error",
                level=AuditLevel.ERROR,
                message=f"{symbol} TP/SL ár hiba: {exc}",
                payload=out,
                strategy_name=self.name,
            )
            return out
        out["tp_source"] = tp_source

        # 7) belépés natív TP/SL-lel (atomi REST hívás a Bitunixhoz)
        request = OrderRequest.model_validate(
            {
                "symbol": symbol,
                "side": side,
                "orderType": "MARKET",
                "quantity": qty,
                "leverage": leverage,
                "tpPrice": tp_price,
                "slPrice": sl_price,
                "tpStopType": stop_type,
                "slStopType": stop_type,
            }
        )

        try:
            order_resp = await trading_service.place_order(
                request, strategy_name=self.name
            )
        except (BitunixAPIError, BitunixSignatureError) as exc:
            out["placed"] = False
            out["reason"] = "place_order_rejected"
            out["error"] = str(exc)
            if isinstance(exc, BitunixAPIError):
                if exc.code is not None:
                    out["bitunix_code"] = exc.code
                if exc.response_body is not None:
                    out["bitunix_response"] = exc.response_body
            await audit.record(
                ctx.session,
                "strategy.top_movers.place_order_failed",
                level=AuditLevel.WARNING,
                message=f"{symbol} rendelés elutasítva: {exc}",
                payload={
                    **out,
                    "quantity": str(qty),
                    "tp_price": str(tp_price),
                    "sl_price": str(sl_price),
                    "leverage": leverage,
                },
                strategy_name=self.name,
            )
            return out

        out.update(
            placed=True,
            side=side,
            leverage=leverage,
            quantity=str(qty),
            entry_price=str(mover.last_price),
            tp_price=str(tp_price),
            sl_price=str(sl_price),
            client_order_id=order_resp.client_order_id,
            dry_run=order_resp.dry_run,
        )
        if tp_source.startswith("calibration") is False:
            out["tp_roi_pct"] = str(tp_roi)
            out["sl_roi_pct"] = str(sl_roi)
        await audit.record(
            ctx.session,
            "strategy.top_movers.tpsl_set",
            level=AuditLevel.INFO,
            message=(
                f"{symbol} {side} entry={mover.last_price} "
                f"tp={tp_price} sl={sl_price} "
                f"(lev={leverage}x, ROI {tp_roi}%/{sl_roi}%)"
            ),
            payload={
                "symbol": symbol,
                "side": side,
                "entry_price": str(mover.last_price),
                "tp_price": str(tp_price),
                "sl_price": str(sl_price),
                "leverage": leverage,
                "tp_roi_pct": str(tp_roi),
                "sl_roi_pct": str(sl_roi),
                "stop_type": stop_type,
            },
            strategy_name=self.name,
        )
        return out

    async def _last_order_at(
        self, ctx: StrategyContext, symbol: str
    ) -> datetime | None:
        """Legutóbbi rendelés idő ennek a stratégiának, ehhez a szimbólumhoz."""
        stmt = (
            sa.select(sa.func.max(Order.created_at))
            .where(Order.strategy_name == self.name)
            .where(Order.symbol == symbol)
        )
        result = await ctx.session.execute(stmt)
        value: datetime | None = result.scalar()
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value


# -- segéd típusok / parser-ek ------------------------------------------------


class _Mover:
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


class _PairMeta:
    __slots__ = ("symbol", "max_leverage", "base_precision", "price_precision")

    def __init__(
        self,
        symbol: str,
        max_leverage: int,
        base_precision: int,
        price_precision: int,
    ) -> None:
        self.symbol = symbol
        self.max_leverage = max_leverage
        self.base_precision = base_precision
        self.price_precision = price_precision


def decide_direction(
    mover: _Mover,
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


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _parse_open_position_symbols(raw: Any) -> set[str]:
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


def _rank_top_movers(raw: Any, *, top_n: int) -> list[_Mover]:
    """Bitunix ticker válaszból top-N mover lista (abszolút % csökkenő)."""
    items = _extract_list(raw)
    movers: list[_Mover] = []
    for item in items:
        symbol = item.get("symbol")
        last = _to_decimal(item.get("lastPrice") or item.get("last"))
        open_p = _to_decimal(item.get("open"))
        if not symbol or last is None or open_p is None or open_p == 0:
            continue
        change_pct = ((last - open_p) / open_p) * Decimal(100)
        high = _to_decimal(item.get("high") or item.get("high24h"))
        low = _to_decimal(item.get("low") or item.get("low24h"))
        movers.append(
            _Mover(
                symbol=symbol,
                last_price=last,
                change_pct=change_pct,
                high=high,
                low=low,
            )
        )
    movers.sort(key=lambda m: abs(m.change_pct), reverse=True)
    return movers[:top_n]


def _index_trading_pairs(raw: Any) -> dict[str, _PairMeta]:
    items = _extract_list(raw)
    out: dict[str, _PairMeta] = {}
    for item in items:
        symbol = item.get("symbol")
        if not symbol:
            continue
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
        out[symbol] = _PairMeta(
            symbol=symbol,
            max_leverage=max_leverage,
            base_precision=base_precision,
            price_precision=price_precision,
        )
    return out


def _extract_list(raw: Any) -> list[dict[str, Any]]:
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


def _extract_available_usdt(raw: Any) -> Decimal:
    """Az ``available`` USDT egyenleg kibontása a ``/futures/account`` válaszból."""
    if isinstance(raw, dict):
        data = raw.get("data", raw)
        if isinstance(data, list) and data:
            data = data[0]
        if isinstance(data, dict):
            for key in ("available", "availableBalance", "balance"):
                val = _to_decimal(data.get(key))
                if val is not None:
                    return val
    return Decimal(0)
