"""Top signal entries stratégia.

A futures piac **top N** (alap: 200) abszolút 24h mozgású szimbólumát
rangsoroljuk ugyanazzal a logikával, mint a ``top_movers``. Ezután csak az
első ``kline_lookahead`` jelöltre kérünk **kline**-t (alap: 40, API terhelés
csökkentése), és **csak akkor** nyitunk pozíciót, ha egyszerre teljesül:

* A 24h ticker alapján van **range** adat, és az ár a mozgás irányához illő
  extrém zónában van (long: felső ``range_threshold``, short: alsó zóna).
* A **|24h % változás|** ≥ konfigurálható minimum.
* **Walk-forward gate (opcionális):** ha ``STRATEGY_TOP_SIGNAL_ENTRIES_WF_GATE_ENABLED``,
  a kline lekérés a ``plan_kline_interval(WF_LOOKBACK)`` szerinti intervallum/limit
  (alap 48h) alapján történik; minden jelöltre lefut a coin-analyze WF variációs
  ajánlás. Csak akkor nyitunk, ha van **ajánlott** variáció (≥80% TP win cél,
  profil + 48h aktivitás; feloldatlan trade nem számít sikernek), a WF irány egyezik a kline belépővel, és a TP/SL
  a WF ``best_current_signal`` százalékai alapján kerül számításra (nem
  kalibrációból).
* A **utolsó lezárt gyertya** (a lista utolsó előtti eleme) **megerősíti** az
  irányt: long esetén bullish zárás és záró > előző gyertya maximuma;
  shortnál bearish zárás és záró < előző gyertya minimuma.

Irány: **BUY** (long) és **SELL** (short) is engedélyezett. TP/SL: WF gate
bekapcsolva a javasolt variáció százalékai; különben kalibráció / ROI fallback
+ ``compute_tp_sl_prices_from_move_pct``, a ``top_movers``-sel megegyezően.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import sqlalchemy as sa

from app.bitunix.exceptions import BitunixAPIError, BitunixSignatureError
from app.db import audit
from app.db.models import AuditLevel, Order
from app.schemas.trading import OrderRequest
from app.services.calibration import parse_klines
from app.services.calibration_runner import get_active_calibration_result
from app.services.coin_analyze import (
    plan_kline_interval,
    walk_forward_live_gate_from_klines,
)
from app.services.risk import compute_margin, compute_quantity
from app.services.strategy.base import Strategy, StrategyContext, StrategyResult
from app.services.strategy.top_movers import (
    _extract_available_usdt,
    _index_trading_pairs,
    _Mover,
    _PairMeta,
    _parse_open_position_symbols,
    _rank_top_movers,
)
from app.services.tpsl import (
    compute_tp_sl_prices_from_move_pct,
    implied_price_move_pct_from_roi,
    implied_tp_roi_pct_from_price_move_pct,
    is_risky_sl_roi,
)
from app.services.trading import TradingService


def entry_side_from_mover_and_klines(
    mover: _Mover,
    klines: list[dict[str, Decimal]],
    *,
    min_abs_change_pct: Decimal,
    range_threshold: Decimal,
) -> tuple[str | None, str]:
    """Kline + 24h ticker alapján belépési irány, vagy ``None`` ha nincs jel.

    Args:
        mover: Rangsorolt ticker (``_Mover``).
        klines: ``parse_klines`` kimenete, idő szerint növekvő.
        min_abs_change_pct: Minimális ``abs(24h change %%)`` a szűréshez.
        range_threshold: Longhoz ``range_position >= threshold``; shorthoz
            ``<= 1 - threshold``.

    Returns:
        ``("BUY"|"SELL"|None, reason)``.
    """
    if len(klines) < 3:
        return None, "insufficient_klines"
    if abs(mover.change_pct) < min_abs_change_pct:
        return None, "min_abs_change_not_met"
    pos = mover.range_position
    if pos is None:
        return None, "no_range_data"

    b = klines[-2]
    a = klines[-3]
    lower = Decimal(1) - range_threshold

    if mover.change_pct > 0 and pos >= range_threshold:
        if b["close"] > b["open"] and b["close"] > a["high"]:
            return "BUY", "long_breakout_confirm"
        return None, "long_range_ok_but_no_kline_confirm"

    if mover.change_pct < 0 and pos <= lower:
        if b["close"] < b["open"] and b["close"] < a["low"]:
            return "SELL", "short_breakdown_confirm"
        return None, "short_range_ok_but_no_kline_confirm"

    return None, "range_or_direction_mismatch"


class TopSignalEntriesStrategy(Strategy):
    """Top mozgók közül kline-megerősített belépés (long + short)."""

    name = "top_signal_entries"

    async def run(self, ctx: StrategyContext) -> StrategyResult:
        result = StrategyResult()
        settings = ctx.settings

        if not settings.strategy_top_signal_entries_enabled:
            await audit.record(
                ctx.session,
                "strategy.skipped",
                level=AuditLevel.INFO,
                message="top_signal_entries ki van kapcsolva (config).",
                strategy_name=self.name,
            )
            result.details["reason"] = "disabled"
            return result

        calibration = await get_active_calibration_result(ctx.session)
        if settings.require_calibration_for_trading and calibration is None:
            await audit.record(
                ctx.session,
                "strategy.top_signal_entries.calibration_missing",
                level=AuditLevel.WARNING,
                message=(
                    "Nincs friss TP/SL kalibráció – a stratégia kihagyja "
                    "a kereskedést, amíg a calibration runner lefut."
                ),
                strategy_name=self.name,
            )
            result.details["reason"] = "calibration_missing"
            return result

        target_slots = max(1, int(settings.strategy_top_signal_entries_count))
        scan_limit = max(
            target_slots,
            min(int(settings.strategy_top_signal_entries_scan_limit), 200),
        )
        lookahead = max(
            target_slots,
            int(settings.strategy_top_signal_entries_kline_lookahead),
        )
        cooldown_minutes = int(settings.strategy_top_signal_entries_cooldown_minutes)
        pct_of_balance = Decimal(settings.strategy_margin_pct_of_balance)
        min_margin = Decimal(settings.strategy_min_margin_usdt)
        min_abs_change = Decimal(settings.strategy_top_signal_entries_min_abs_change_pct)
        range_threshold = Decimal(settings.strategy_top_signal_entries_range_threshold)
        kline_interval = settings.strategy_top_signal_entries_kline_interval
        kline_limit = min(
            200,
            max(3, int(settings.strategy_top_signal_entries_kline_limit)),
        )
        wf_gate = settings.strategy_top_signal_entries_wf_gate_enabled
        wf_lb = int(settings.strategy_top_signal_entries_wf_lookback_minutes)
        fetch_interval = kline_interval
        fetch_limit = kline_limit
        if wf_gate:
            planned_iv, planned_lim = plan_kline_interval(wf_lb)
            fetch_interval = planned_iv
            fetch_limit = max(kline_limit, planned_lim)
        max_conc = max(1, int(settings.strategy_top_signal_entries_max_kline_concurrency))

        result.details["walk_forward_gate"] = {
            "enabled": wf_gate,
            "lookback_minutes": wf_lb,
            "kline_fetch_interval": fetch_interval,
            "kline_fetch_limit": fetch_limit,
        }

        tickers_raw = await ctx.client.get_all_tickers()
        pairs_raw = await ctx.client.get_trading_pairs()

        movers = _rank_top_movers(tickers_raw, top_n=scan_limit)
        pair_meta = _index_trading_pairs(pairs_raw)
        candidates = movers[: min(lookahead, len(movers))]

        try:
            pos_raw = await ctx.client.get_positions()
            open_syms = _parse_open_position_symbols(pos_raw)
        except (BitunixAPIError, BitunixSignatureError) as exc:
            await audit.record(
                ctx.session,
                "strategy.top_signal_entries.positions_error",
                level=AuditLevel.WARNING,
                message=f"Pozíciók lekérése sikertelen: {exc}",
                payload={"error": str(exc)},
                strategy_name=self.name,
            )
            open_syms = set()
        except Exception as exc:  # noqa: BLE001
            await audit.record(
                ctx.session,
                "strategy.top_signal_entries.positions_error",
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
            "strategy.top_signal_entries.ranked",
            level=AuditLevel.INFO,
            message=(
                f"Top {len(movers)} / scan={scan_limit}, kline jelöltek: {len(candidates)}, "
                f"nyitott: {total_open}, kitöltendő slot: {need}."
            ),
            payload={
                "target_slots": target_slots,
                "scan_limit": scan_limit,
                "kline_lookahead": lookahead,
                "open_symbols_sample": sorted(open_syms)[:40],
                "slots_to_fill": need,
            },
            strategy_name=self.name,
        )

        try:
            account_raw = await ctx.client.get_account(settings.bitunix_margin_coin)
        except (BitunixAPIError, BitunixSignatureError) as exc:
            await audit.record(
                ctx.session,
                "strategy.top_signal_entries.balance_error",
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

        tp_roi = Decimal(settings.strategy_tp_roi_pct)
        sl_roi = Decimal(settings.strategy_sl_roi_pct)
        result.details["calibration_used"] = calibration is not None
        if calibration is None and is_risky_sl_roi(sl_roi):
            await audit.record(
                ctx.session,
                "strategy.top_signal_entries.risky_sl_warning",
                level=AuditLevel.WARNING,
                message=f"SL ROI {sl_roi}% magas (likvidáció-közeli).",
                payload={"sl_roi_pct": str(sl_roi)},
                strategy_name=self.name,
            )

        cooldown_until_after = datetime.now(UTC) - timedelta(minutes=cooldown_minutes)
        trading_service = TradingService(ctx.client, ctx.session)
        stop_type = settings.strategy_tpsl_stop_type

        result.details["position_slots"] = {
            "target": target_slots,
            "scan_limit": scan_limit,
            "total_open_positions": total_open,
            "slots_to_fill": need,
        }

        placed_run = 0
        if need > 0:
            sem = asyncio.Semaphore(max_conc)

            async def fetch_klines(symbol: str) -> tuple[str, dict[str, Any] | None, str | None]:
                async with sem:
                    try:
                        raw = await ctx.client.get_klines(
                            symbol,
                            interval=fetch_interval,
                            limit=fetch_limit,
                        )
                        return symbol, raw, None
                    except (BitunixAPIError, BitunixSignatureError) as exc:
                        return symbol, None, str(exc)
                    except Exception as exc:  # noqa: BLE001
                        return symbol, None, str(exc)

            fetch_tasks = [asyncio.create_task(fetch_klines(m.symbol)) for m in candidates]
            kline_by_symbol: dict[str, dict[str, Any]] = {}
            kline_errors: dict[str, str] = {}
            for t in asyncio.as_completed(fetch_tasks):
                sym, raw, err = await t
                if err is not None:
                    kline_errors[sym] = err
                elif raw is not None:
                    kline_by_symbol[sym] = raw

            for mover in candidates:
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

                raw_k = kline_by_symbol.get(mover.symbol)
                if raw_k is None:
                    err = kline_errors.get(mover.symbol, "missing_kline_response")
                    result.skipped.append(
                        {
                            "symbol": mover.symbol,
                            "placed": False,
                            "reason": "klines_error",
                            "error": err,
                            "change_pct": str(mover.change_pct),
                        }
                    )
                    continue

                klines = parse_klines(raw_k)
                side, signal_reason = entry_side_from_mover_and_klines(
                    mover,
                    klines,
                    min_abs_change_pct=min_abs_change,
                    range_threshold=range_threshold,
                )
                if side is None:
                    result.skipped.append(
                        {
                            "symbol": mover.symbol,
                            "placed": False,
                            "reason": "no_entry_signal",
                            "signal_detail": signal_reason,
                            "change_pct": str(mover.change_pct),
                        }
                    )
                    continue

                wf_moves: tuple[Decimal, Decimal] | None = None
                wf_audit: dict[str, Any] | None = None
                wf_gate_result: dict[str, Any] | None = None
                if wf_gate:
                    wf = walk_forward_live_gate_from_klines(
                        klines,
                        choppiness_max=Decimal(
                            settings.strategy_top_signal_entries_wf_choppiness_max
                        ),
                        walk_forward_cooldown_minutes=int(
                            settings.strategy_top_signal_entries_wf_cooldown_minutes
                        ),
                    )
                    if not wf["ok"]:
                        result.skipped.append(
                            {
                                "symbol": mover.symbol,
                                "placed": False,
                                "reason": "walk_forward_gate",
                                "wf_reason": wf["reason"],
                                "wf_detail": wf.get("detail"),
                                "change_pct": str(mover.change_pct),
                            }
                        )
                        continue
                    wf_side = wf["side"]
                    if wf_side != side:
                        result.skipped.append(
                            {
                                "symbol": mover.symbol,
                                "placed": False,
                                "reason": "walk_forward_side_mismatch",
                                "entry_signal_side": side,
                                "wf_side": wf_side,
                                "change_pct": str(mover.change_pct),
                            }
                        )
                        continue
                    wf_moves = (wf["tp_move_pct"], wf["sl_move_pct"])
                    wf_gate_result = wf
                    wf_audit = {
                        "wf_tp_median_multiplier": wf.get("tp_median_multiplier"),
                        "wf_sl_median_multiplier": wf.get("sl_median_multiplier"),
                        "wf_prediction_reason": wf.get("prediction_reason"),
                        "wf_gate_source": wf.get("wf_gate_source"),
                        "wf_resolved_tp_win_rate_pct": (
                            (wf.get("wf_variation_snapshot") or {}).get(
                                "resolved_tp_win_rate_pct"
                            )
                        ),
                    }

                decision = await self._place_confirmed(
                    ctx,
                    mover=mover,
                    side=side,
                    signal_reason=signal_reason,
                    pair_meta=pair_meta,
                    margin_usdt=margin_usdt,
                    cooldown_after=cooldown_until_after,
                    trading_service=trading_service,
                    tp_roi=tp_roi,
                    sl_roi=sl_roi,
                    stop_type=stop_type,
                    calibration=calibration,
                    wf_move_pct_pair=wf_moves,
                    wf_audit=wf_audit if wf_gate else None,
                    wf_gate_result=wf_gate_result,
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
                "strategy.top_signal_entries.slots_full",
                level=AuditLevel.INFO,
                message=(
                    f"Nincs új belépés: {total_open} nyitott pozíció ≥ "
                    f"{target_slots} slot cél."
                ),
                strategy_name=self.name,
            )

        result.details["position_slots"]["placed_this_run"] = placed_run
        return result

    async def _place_confirmed(
        self,
        ctx: StrategyContext,
        *,
        mover: _Mover,
        side: str,
        signal_reason: str,
        pair_meta: dict[str, _PairMeta],
        margin_usdt: Decimal,
        cooldown_after: datetime,
        trading_service: TradingService,
        tp_roi: Decimal,
        sl_roi: Decimal,
        stop_type: str,
        calibration: Any | None,
        wf_move_pct_pair: tuple[Decimal, Decimal] | None = None,
        wf_audit: dict[str, Any] | None = None,
        wf_gate_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        symbol = mover.symbol
        out: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "signal_reason": signal_reason,
            "change_pct": str(mover.change_pct),
        }
        if wf_audit:
            out.update(wf_audit)

        last = await self._last_order_at(ctx, symbol)
        if last and last > cooldown_after:
            out["placed"] = False
            out["reason"] = "cooldown"
            out["last_order_at"] = last.isoformat()
            await audit.record(
                ctx.session,
                "strategy.top_signal_entries.cooldown_skip",
                level=AuditLevel.INFO,
                message=f"{symbol} cooldownban (utolsó: {last.isoformat()}).",
                payload=out,
                strategy_name=self.name,
            )
            return out

        meta = pair_meta.get(symbol)
        if meta is None:
            out["placed"] = False
            out["reason"] = "no_trading_pair_metadata"
            await audit.record(
                ctx.session,
                "strategy.top_signal_entries.no_metadata",
                level=AuditLevel.WARNING,
                message=f"{symbol} nincs a trading_pairs listában.",
                payload=out,
                strategy_name=self.name,
            )
            return out

        leverage = max(1, int(meta.max_leverage))

        qty = compute_quantity(
            margin_usdt=margin_usdt,
            leverage=leverage,
            price=mover.last_price,
            base_precision=meta.base_precision,
        )
        if qty <= 0:
            out["placed"] = False
            out["reason"] = "quantity_rounded_to_zero"
            return out

        tp_source = "roi_fallback"
        try:
            if wf_move_pct_pair is not None:
                tp_move_pct, sl_move_pct = wf_move_pct_pair
                tp_source = "walk_forward_recommendation"
            elif calibration is not None:
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
            min_tp_roi = Decimal(ctx.settings.strategy_min_tp_roi_pct)
            if min_tp_roi > 0:
                implied_tp_roi = implied_tp_roi_pct_from_price_move_pct(
                    tp_move_pct=tp_move_pct, leverage=leverage
                )
                if implied_tp_roi < min_tp_roi:
                    out["placed"] = False
                    out["reason"] = "tp_roi_below_min"
                    out["implied_tp_roi_pct"] = str(implied_tp_roi)
                    out["min_tp_roi_pct"] = str(min_tp_roi)
                    out["tp_move_pct"] = str(tp_move_pct)
                    await audit.record(
                        ctx.session,
                        "strategy.top_signal_entries.tp_roi_below_min",
                        level=AuditLevel.INFO,
                        message=(
                            f"{symbol} kihagyva: TP margin-ROI {implied_tp_roi}% < "
                            f"minimum {min_tp_roi}% (tp_move={tp_move_pct}%, lev={leverage}x)."
                        ),
                        payload=out,
                        strategy_name=self.name,
                    )
                    return out
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
                "strategy.top_signal_entries.tpsl_error",
                level=AuditLevel.ERROR,
                message=f"{symbol} TP/SL hiba: {exc}",
                payload=out,
                strategy_name=self.name,
            )
            return out
        out["tp_source"] = tp_source

        entry_context: dict[str, Any] = {
            "strategy": self.name,
            "signal_reason": signal_reason,
            "change_pct_24h": str(mover.change_pct),
            "tp_source": tp_source,
            "tp_move_pct": str(tp_move_pct),
            "sl_move_pct": str(sl_move_pct),
        }
        if isinstance(wf_gate_result, dict) and wf_gate_result.get("ok"):
            entry_context["walk_forward"] = {
                "gate_source": wf_gate_result.get("wf_gate_source"),
                "prediction_reason": wf_gate_result.get("prediction_reason"),
                "target_tp_win_rate_pct": wf_gate_result.get(
                    "wf_target_tp_win_rate_pct"
                ),
                "variation": wf_gate_result.get("wf_variation_snapshot"),
            }

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
                request,
                strategy_name=self.name,
                entry_context=entry_context,
            )
        except (BitunixAPIError, BitunixSignatureError) as exc:
            out["placed"] = False
            out["reason"] = "place_order_rejected"
            out["error"] = str(exc)
            await audit.record(
                ctx.session,
                "strategy.top_signal_entries.place_order_failed",
                level=AuditLevel.WARNING,
                message=f"{symbol} rendelés elutasítva: {exc}",
                payload={**out, "quantity": str(qty)},
                strategy_name=self.name,
            )
            return out

        out.update(
            placed=True,
            leverage=leverage,
            quantity=str(qty),
            entry_price=str(mover.last_price),
            tp_price=str(tp_price),
            sl_price=str(sl_price),
            client_order_id=order_resp.client_order_id,
            dry_run=order_resp.dry_run,
            entry_context=entry_context,
        )
        await audit.record(
            ctx.session,
            "strategy.top_signal_entries.order_placed",
            level=AuditLevel.INFO,
            message=f"{symbol} {side} {signal_reason} entry={mover.last_price}",
            payload=out,
            strategy_name=self.name,
        )
        return out

    async def _last_order_at(self, ctx: StrategyContext, symbol: str) -> datetime | None:
        stmt = (
            sa.select(sa.func.max(Order.created_at))
            .where(Order.strategy_name == self.name)
            .where(Order.symbol == symbol)
        )
        res = await ctx.session.execute(stmt)
        value: datetime | None = res.scalar()
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value
