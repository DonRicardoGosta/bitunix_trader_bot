"""Analytics aggregációk — idősorok, ablakos statisztikák."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

_ANALYTICS_TZ = ZoneInfo("Europe/Budapest")
_WEEKDAY_LABELS_HU = (
    "Hétfő",
    "Kedd",
    "Szerda",
    "Csütörtök",
    "Péntek",
    "Szombat",
    "Vasárnap",
)

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.bitunix.client import BitunixClient
from app.bitunix.exceptions import BitunixAPIError, BitunixSignatureError
from app.db.models import Order, StrategyRun
from app.services.dashboard import _dec, _q2
from app.services.analytics_window import ResolvedAnalyticsWindow, resolve_analytics_window
from app.services.position_history import (
    fetch_closed_positions_in_lookback,
    fetch_closed_positions_in_window,
    position_event_time,
)


def _bucket_start(dt: datetime, bucket_hours: int) -> datetime:
    epoch = int(dt.timestamp())
    bucket_sec = max(1, bucket_hours) * 3600
    aligned = (epoch // bucket_sec) * bucket_sec
    return datetime.fromtimestamp(aligned, tz=UTC)


def _iter_bucket_range(
    since: datetime, end: datetime, bucket_hours: int
) -> list[datetime]:
    """Minden bucket kezdete a [since, end] ablakon belül (üres bucketekkel)."""
    if end < since:
        return []
    step = timedelta(hours=max(1, bucket_hours))
    start = _bucket_start(since, bucket_hours)
    out: list[datetime] = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur += step
    return out


def _positions_breakdown(
    closed: list[dict[str, Any]],
) -> dict[str, Any]:
    """Szimbólum, oldal, top trade lista."""
    per_symbol: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    by_side: dict[str, dict[str, int]] = defaultdict(
        lambda: {"count": 0, "wins": 0, "losses": 0}
    )
    trade_rows: list[tuple[Decimal, dict[str, Any]]] = []

    for p in closed:
        r = _dec(p.get("realized_pnl"))
        if r is None:
            continue
        sym = p.get("symbol") or "?"
        per_symbol[sym] += r
        side = (p.get("side") or "?").upper()
        by_side[side]["count"] += 1
        if r > 0:
            by_side[side]["wins"] += 1
        elif r < 0:
            by_side[side]["losses"] += 1
        trade_rows.append((r, p))

    per_symbol_list = sorted(
        (
            {"symbol": s, "realized_pnl_usdt": str(v), "count": 0}
            for s, v in per_symbol.items()
        ),
        key=lambda x: Decimal(x["realized_pnl_usdt"]),
        reverse=True,
    )
    sym_counts: dict[str, int] = defaultdict(int)
    for p in closed:
        if p.get("symbol"):
            sym_counts[p["symbol"]] += 1
    for row in per_symbol_list:
        row["count"] = sym_counts.get(row["symbol"], 0)

    trade_rows.sort(key=lambda x: x[0], reverse=True)
    top_winners = [
        {
            "symbol": p.get("symbol"),
            "side": p.get("side"),
            "realized_pnl_usdt": str(r),
            "closed_at": p.get("closed_at") or p.get("updated_at"),
            "roi_pct": p.get("roi_pct"),
        }
        for r, p in trade_rows[:8]
        if r > 0
    ]
    top_losers = [
        {
            "symbol": p.get("symbol"),
            "side": p.get("side"),
            "realized_pnl_usdt": str(r),
            "closed_at": p.get("closed_at") or p.get("updated_at"),
            "roi_pct": p.get("roi_pct"),
        }
        for r, p in reversed(trade_rows[-8:])
        if r < 0
    ][:8]

    return {
        "per_symbol": per_symbol_list[:12],
        "by_side": dict(by_side),
        "top_winners": top_winners,
        "top_losers": top_losers,
    }


async def _fetch_closed_for_window(
    client: BitunixClient,
    window: ResolvedAnalyticsWindow,
) -> tuple[list[dict[str, Any]], str | None]:
    if window.custom:
        return await fetch_closed_positions_in_window(
            client, since=window.since, until=window.until
        )
    return await fetch_closed_positions_in_lookback(
        client, lookback_hours=window.lookback_hours
    )


def _empty_hour_buckets() -> list[dict[str, int]]:
    return [{"hour": h, "tp_count": 0, "sl_count": 0} for h in range(24)]


def _tp_sl_timing_stats(closed: list[dict[str, Any]]) -> dict[str, Any]:
    """Lezárt pozíciók TP/SL darabszáma óra (0–23) és hét napja szerint.

    A Bitunix history nem ad explicit TP/SL típust; közelítés:
    realizált PnL > 0 → TP (nyereséges zárás), < 0 → SL (vesztes zárás).
    Időbélyeg: lezárás (``closed_at`` / ``updated_at``), napok/hetek összesítve.

    ``by_hour`` / ``by_weekday``: az ablak összes napja együtt.
    ``by_weekday_hour``: hét napja × óra — pl. minden hétfő 14:00-ja összeadódik.
    """
    by_hour = _empty_hour_buckets()
    by_weekday: list[dict[str, int | str]] = [
        {
            "weekday": wd,
            "label": _WEEKDAY_LABELS_HU[wd],
            "tp_count": 0,
            "sl_count": 0,
        }
        for wd in range(7)
    ]
    by_weekday_hour: list[dict[str, Any]] = [
        {
            "weekday": wd,
            "label": _WEEKDAY_LABELS_HU[wd],
            "by_hour": _empty_hour_buckets(),
        }
        for wd in range(7)
    ]
    for p in closed:
        r = _dec(p.get("realized_pnl"))
        if r is None or r == 0:
            continue
        ts = position_event_time(p)
        if ts is None:
            continue
        local = ts.astimezone(_ANALYTICS_TZ)
        hour = local.hour
        wd = local.weekday()
        wd_hours = by_weekday_hour[wd]["by_hour"]
        if r > 0:
            by_hour[hour]["tp_count"] += 1
            by_weekday[wd]["tp_count"] += 1
            wd_hours[hour]["tp_count"] += 1
        else:
            by_hour[hour]["sl_count"] += 1
            by_weekday[wd]["sl_count"] += 1
            wd_hours[hour]["sl_count"] += 1
    total_tp = sum(b["tp_count"] for b in by_hour)
    total_sl = sum(b["sl_count"] for b in by_hour)
    return {
        "timezone": "Europe/Budapest",
        "classification_note": (
            "TP = nyereséges lezárás (realized PnL > 0), "
            "SL = vesztes lezárás (realized PnL < 0). "
            "Órák és napok külön-külön az ablak összes napján összesítve; "
            "a nap+óra nézet ugyanazon hét napjának minden előfordulását összeadja "
            "(pl. két hétfő 10:00-ja egy sorban)."
        ),
        "by_hour": by_hour,
        "by_weekday": by_weekday,
        "by_weekday_hour": by_weekday_hour,
        "total_tp": total_tp,
        "total_sl": total_sl,
    }


def _closed_kpis(realized_pnls: list[Decimal]) -> dict[str, Any]:
    wins = [v for v in realized_pnls if v > 0]
    losses = [v for v in realized_pnls if v < 0]
    total = len(realized_pnls)
    realized_sum = sum(realized_pnls, Decimal(0))
    gross_profit = sum(wins, Decimal(0))
    gross_loss_abs = abs(sum(losses, Decimal(0)))
    profit_factor: str | None = None
    if gross_loss_abs > 0:
        profit_factor = _q2(gross_profit / gross_loss_abs)
    win_rate = (Decimal(len(wins)) / Decimal(total) * 100) if total else None
    avg_win = gross_profit / Decimal(len(wins)) if wins else None
    avg_loss = sum(losses, Decimal(0)) / Decimal(len(losses)) if losses else None
    expectancy: str | None = None
    if total > 0 and avg_win is not None and avg_loss is not None:
        wr = Decimal(len(wins)) / Decimal(total)
        lr = Decimal(len(losses)) / Decimal(total)
        exp = avg_win * wr + avg_loss * lr
        expectancy = str(exp.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))

    # Max drawdown a kumulatív realized görbén (időrend szerint)
    max_dd = Decimal(0)
    peak = Decimal(0)
    cumulative = Decimal(0)
    for v in realized_pnls:
        cumulative += v
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd

    return {
        "count": total,
        "realized_pnl_usdt": str(realized_sum),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": _q2(win_rate) if win_rate is not None else None,
        "profit_factor": profit_factor,
        "expectancy_usdt": expectancy,
        "max_drawdown_usdt": str(max_dd.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
        "avg_win_usdt": str(avg_win) if avg_win is not None else None,
        "avg_loss_usdt": str(avg_loss) if avg_loss is not None else None,
    }


async def build_pnl_series(
    client: BitunixClient | None,
    *,
    window: ResolvedAnalyticsWindow,
    bucket_hours: int = 1,
) -> dict[str, Any]:
    """Lezárt pozíciók realized PnL idősora bucketenként."""
    since = window.since
    until = window.until
    lookback_hours = window.lookback_hours

    if client is None:
        return {
            "lookback_hours": lookback_hours,
            "window_custom": window.custom,
            "window_end_live": window.end_live,
            "bucket_hours": bucket_hours,
            "window_start": since.isoformat(),
            "window_end": until.isoformat(),
            "positions_in_window": 0,
            "sync_error": "Bitunix API kulcs hiányzik.",
            "buckets": [],
            "cumulative": [],
            "kpis": _closed_kpis([]),
            "breakdown": _positions_breakdown([]),
            "tp_sl_timing": _tp_sl_timing_stats([]),
        }

    closed, sync_error = await _fetch_closed_for_window(client, window)
    bucket_map: dict[datetime, Decimal] = defaultdict(lambda: Decimal(0))
    series_points: list[tuple[datetime, Decimal]] = []

    for p in closed:
        r = _dec(p.get("realized_pnl"))
        if r is None:
            continue
        ts = position_event_time(p)
        if ts is None or ts < since or ts > until:
            continue
        series_points.append((ts, r))
        b = _bucket_start(ts, bucket_hours)
        bucket_map[b] += r

    series_points.sort(key=lambda x: x[0])
    realized_pnls = [v for _, v in series_points]

    bucket_starts = _iter_bucket_range(since, until, bucket_hours)
    buckets = [
        {
            "bucket_start": b.isoformat(),
            "realized_pnl_usdt": str(
                bucket_map.get(b, Decimal(0)).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )
            ),
        }
        for b in bucket_starts
    ]

    cumulative: list[dict[str, str]] = [
        {"at": since.isoformat(), "cumulative_pnl_usdt": "0"}
    ]
    running = Decimal(0)
    for ts, v in series_points:
        running += v
        cumulative.append(
            {
                "at": ts.isoformat(),
                "cumulative_pnl_usdt": str(
                    running.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                ),
            }
        )
    if len(cumulative) == 1:
        cumulative.append(
            {
                "at": until.isoformat(),
                "cumulative_pnl_usdt": "0",
            }
        )

    return {
        "lookback_hours": lookback_hours,
        "window_custom": window.custom,
        "window_end_live": window.end_live,
        "bucket_hours": bucket_hours,
        "window_start": since.isoformat(),
        "window_end": until.isoformat(),
        "positions_in_window": len(closed),
        "sync_error": sync_error,
        "buckets": buckets,
        "cumulative": cumulative,
        "kpis": _closed_kpis(realized_pnls),
        "breakdown": _positions_breakdown(closed),
        "tp_sl_timing": _tp_sl_timing_stats(closed),
    }


async def build_analytics_summary(
    session: AsyncSession,
    client: BitunixClient | None,
    *,
    window: ResolvedAnalyticsWindow,
    bucket_hours: int = 1,
) -> dict[str, Any]:
    """Egy válaszban: PnL idősor + DB rendelés/stratégia + bontások."""
    pnl = await build_pnl_series(client, window=window, bucket_hours=bucket_hours)
    orders = await build_orders_window_stats(session, window=window)
    strategy = await build_strategy_runs_window_stats(session, window=window)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "lookback_hours": window.lookback_hours,
        "window_custom": window.custom,
        "window_end_live": window.end_live,
        "window_start": window.since.isoformat(),
        "window_end": window.until.isoformat(),
        "bucket_hours": bucket_hours,
        "pnl": pnl,
        "orders": orders,
        "strategy": strategy,
    }


async def build_orders_window_stats(
    session: AsyncSession, *, window: ResolvedAnalyticsWindow
) -> dict[str, Any]:
    since, until = window.since, window.until
    total = (
        await session.execute(
            sa.select(sa.func.count())
            .select_from(Order)
            .where(Order.created_at >= since, Order.created_at <= until)
        )
    ).scalar_one()
    rows = (
        await session.execute(
            sa.select(Order.status, sa.func.count())
            .where(Order.created_at >= since, Order.created_at <= until)
            .group_by(Order.status)
        )
    ).all()
    by_status = {s.value if hasattr(s, "value") else str(s): int(c) for s, c in rows}
    strat_rows = (
        await session.execute(
            sa.select(Order.strategy_name, sa.func.count())
            .where(Order.created_at >= since, Order.created_at <= until)
            .group_by(Order.strategy_name)
            .order_by(sa.func.count().desc())
        )
    ).all()
    by_strategy = [
        {"strategy": s or "(manuális)", "count": int(c)} for s, c in strat_rows
    ]
    return {
        "lookback_hours": window.lookback_hours,
        "window_custom": window.custom,
        "window_end_live": window.end_live,
        "window_start": since.isoformat(),
        "window_end": until.isoformat(),
        "total": int(total),
        "by_status": by_status,
        "by_strategy": by_strategy,
    }


async def build_strategy_runs_window_stats(
    session: AsyncSession, *, window: ResolvedAnalyticsWindow
) -> dict[str, Any]:
    since, until = window.since, window.until
    rows = (
        await session.execute(
            sa.select(StrategyRun.status, sa.func.count())
            .where(StrategyRun.started_at >= since, StrategyRun.started_at <= until)
            .group_by(StrategyRun.status)
        )
    ).all()
    by_status = {st.value if hasattr(st, "value") else str(st): int(c) for st, c in rows}
    return {
        "lookback_hours": window.lookback_hours,
        "window_custom": window.custom,
        "window_end_live": window.end_live,
        "window_start": since.isoformat(),
        "window_end": until.isoformat(),
        "by_status": by_status,
    }
