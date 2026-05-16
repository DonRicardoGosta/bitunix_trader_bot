"""Analytics aggregációk — idősorok, ablakos statisztikák."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.bitunix.client import BitunixClient
from app.bitunix.exceptions import BitunixAPIError, BitunixSignatureError
from app.db.models import Order, StrategyRun
from app.services.dashboard import _dec, _q2
from app.services.position_history import (
    fetch_closed_positions_in_lookback,
    position_event_time,
)


def _bucket_start(dt: datetime, bucket_hours: int) -> datetime:
    epoch = int(dt.timestamp())
    bucket_sec = max(1, bucket_hours) * 3600
    aligned = (epoch // bucket_sec) * bucket_sec
    return datetime.fromtimestamp(aligned, tz=UTC)


async def _fetch_closed_in_window(
    client: BitunixClient,
    *,
    lookback_hours: int,
) -> tuple[list[dict[str, Any]], str | None]:
    return await fetch_closed_positions_in_lookback(
        client, lookback_hours=lookback_hours
    )


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
    lookback_hours: int,
    bucket_hours: int = 1,
) -> dict[str, Any]:
    """Lezárt pozíciók realized PnL idősora bucketenként."""
    if client is None:
        return {
            "lookback_hours": lookback_hours,
            "bucket_hours": bucket_hours,
            "sync_error": "Bitunix API kulcs hiányzik.",
            "buckets": [],
            "cumulative": [],
            "kpis": _closed_kpis([]),
        }

    closed, sync_error = await _fetch_closed_in_window(
        client, lookback_hours=lookback_hours
    )
    bucket_map: dict[datetime, Decimal] = defaultdict(lambda: Decimal(0))
    series_points: list[tuple[datetime, Decimal]] = []

    for p in closed:
        r = _dec(p.get("realized_pnl"))
        if r is None:
            continue
        ts = position_event_time(p)
        if ts is None:
            continue
        series_points.append((ts, r))
        b = _bucket_start(ts, bucket_hours)
        bucket_map[b] += r

    series_points.sort(key=lambda x: x[0])
    realized_pnls = [v for _, v in series_points]

    buckets = [
        {
            "bucket_start": b.isoformat(),
            "realized_pnl_usdt": str(v),
        }
        for b, v in sorted(bucket_map.items())
    ]
    cumulative: list[dict[str, str]] = []
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

    return {
        "lookback_hours": lookback_hours,
        "bucket_hours": bucket_hours,
        "sync_error": sync_error,
        "buckets": buckets,
        "cumulative": cumulative[-500:],
        "kpis": _closed_kpis(realized_pnls),
    }


async def build_orders_window_stats(
    session: AsyncSession, *, lookback_hours: int
) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(hours=lookback_hours)
    total = (
        await session.execute(
            sa.select(sa.func.count())
            .select_from(Order)
            .where(Order.created_at >= since)
        )
    ).scalar_one()
    rows = (
        await session.execute(
            sa.select(Order.status, sa.func.count())
            .where(Order.created_at >= since)
            .group_by(Order.status)
        )
    ).all()
    by_status = {s.value if hasattr(s, "value") else str(s): int(c) for s, c in rows}
    strat_rows = (
        await session.execute(
            sa.select(Order.strategy_name, sa.func.count())
            .where(Order.created_at >= since)
            .group_by(Order.strategy_name)
            .order_by(sa.func.count().desc())
        )
    ).all()
    by_strategy = [
        {"strategy": s or "(manuális)", "count": int(c)} for s, c in strat_rows
    ]
    return {
        "lookback_hours": lookback_hours,
        "total": int(total),
        "by_status": by_status,
        "by_strategy": by_strategy,
    }


async def build_strategy_runs_window_stats(
    session: AsyncSession, *, lookback_hours: int
) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(hours=lookback_hours)
    rows = (
        await session.execute(
            sa.select(StrategyRun.status, sa.func.count())
            .where(StrategyRun.started_at >= since)
            .group_by(StrategyRun.status)
        )
    ).all()
    by_status = {st.value if hasattr(st, "value") else str(st): int(c) for st, c in rows}
    return {"lookback_hours": lookback_hours, "by_status": by_status}
