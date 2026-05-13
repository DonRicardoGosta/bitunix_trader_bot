"""Top Movers stratégia.

Specifikáció:

* Kérdezzük le a Bitunix futures piac **összes szimbólumát** 24h tickerekkel.
* Rangsoroljuk őket az **abszolút** 24h % változás szerint csökkenő sorrendben
  (függetlenül attól, hogy fel- vagy le-mozdulás).
* Vegyük a **top 3-at**.
* Minden szimbólumra:
    * **Cooldown:** ha 4 órán belül már nyitottunk ugyanennek a stratégiának
      ezzel a szimbólummal, kihagyjuk.
    * **Leverage:** lekérdezzük a ``trading_pairs``-ből a ``maxLeverage``-t,
      és beállítjuk az adott szimbólumra.
    * **Margin:** a futures USDT egyenleg 1%-a, de minimum 0.25 USDT.
    * **Irány:** trend-követő – ha +% → BUY (LONG), ha −% → SELL (SHORT).
    * Piaci rendelés.

Megjegyzés: a Bitunix dokumentáció ``lastPrice`` és ``open`` mezőket ad
24h ticker-ben → a változás % így számolt: ``(last - open) / open × 100``.
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
from app.services.risk import compute_margin, compute_quantity
from app.services.strategy.base import Strategy, StrategyContext, StrategyResult
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

        top_n = max(1, int(settings.strategy_top_movers_count))
        cooldown_minutes = int(settings.strategy_top_movers_cooldown_minutes)
        pct_of_balance = Decimal(settings.strategy_margin_pct_of_balance)
        min_margin = Decimal(settings.strategy_min_margin_usdt)

        # 1) tickers + 2) trading pairs (max leverage + precíziók) párhuzamos lekérése
        tickers_raw = await ctx.client.get_all_tickers()
        pairs_raw = await ctx.client.get_trading_pairs()

        movers = _rank_top_movers(tickers_raw, top_n=top_n)
        pair_meta = _index_trading_pairs(pairs_raw)

        await audit.record(
            ctx.session,
            "strategy.top_movers.ranked",
            level=AuditLevel.INFO,
            message=f"Top {len(movers)} mover kiválasztva.",
            payload={
                "top_n": top_n,
                "candidates": [
                    {"symbol": m.symbol, "change_pct": str(m.change_pct), "last": str(m.last_price)}
                    for m in movers
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

        # 4) Iteráció a top-n moveren
        for mover in movers:
            decision = await self._maybe_place(
                ctx,
                mover=mover,
                pair_meta=pair_meta,
                margin_usdt=margin_usdt,
                cooldown_after=cooldown_until_after,
                trading_service=trading_service,
            )
            if decision.get("placed"):
                result.placed_orders.append(decision)
            else:
                result.skipped.append(decision)

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
    ) -> dict[str, Any]:
        """Egy szimbólumra a teljes döntéslánc + végrehajtás."""
        symbol = mover.symbol
        out: dict[str, Any] = {"symbol": symbol, "change_pct": str(mover.change_pct)}

        # cooldown
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

        leverage = max(1, int(meta.max_leverage))

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

        side = "BUY" if mover.change_pct >= 0 else "SELL"
        request = OrderRequest.model_validate(
            {
                "symbol": symbol,
                "side": side,
                "orderType": "MARKET",
                "quantity": qty,
                "leverage": leverage,
            }
        )

        order_resp = await trading_service.place_order(request, strategy_name=self.name)
        out.update(
            placed=True,
            side=side,
            leverage=leverage,
            quantity=str(qty),
            client_order_id=order_resp.client_order_id,
            dry_run=order_resp.dry_run,
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
    __slots__ = ("symbol", "last_price", "change_pct")

    def __init__(self, symbol: str, last_price: Decimal, change_pct: Decimal) -> None:
        self.symbol = symbol
        self.last_price = last_price
        self.change_pct = change_pct


class _PairMeta:
    __slots__ = ("symbol", "max_leverage", "base_precision")

    def __init__(
        self, symbol: str, max_leverage: int, base_precision: int
    ) -> None:
        self.symbol = symbol
        self.max_leverage = max_leverage
        self.base_precision = base_precision


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


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
        movers.append(_Mover(symbol=symbol, last_price=last, change_pct=change_pct))
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
        out[symbol] = _PairMeta(
            symbol=symbol,
            max_leverage=max_leverage,
            base_precision=base_precision,
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
