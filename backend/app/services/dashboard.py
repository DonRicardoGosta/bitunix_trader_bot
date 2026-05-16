"""Dashboard összesítő — KPI-k a kezdőlaphoz.

A cél: egy hívással elég adat ahhoz, hogy a frontend főoldalon érdemi
áttekintést kapjon a felhasználó. Forrás:

* DB ``orders`` tábla — saját rendelések audit-ja, status / strategy bontás.
* DB ``audit_events`` — legutóbbi események count + szint szerint.
* Bitunix ``get_pending_positions`` — nyitott exposure, unrealized PnL.
* Bitunix ``get_history_positions`` (szimbólumonként, az utolsó N nap) —
  lezárt pozíciók, realizált PnL, win-rate, top winners/losers.

Az aggregáció felfelé van skálázva: ha Bitunix nem érhető el, a DB rész
attól még megjön (graceful degradation), és a hiba egy ``sync_error``
mezőben látható.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.bitunix.client import BitunixClient
from app.bitunix.exceptions import BitunixAPIError, BitunixSignatureError
from app.db.models import (
    AuditEvent,
    AuditLevel,
    Order,
    StrategyRun,
    StrategyRunStatus,
    TpSlCalibration,
)
from app.services.order_enrichment import extract_open_position_rows
from app.services.position_history import fetch_closed_positions_in_lookback
from app.services.positions_normalize import normalize_position_row


def _dec(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _q2(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


async def _orders_summary(
    session: AsyncSession, *, lookback_hours: int | None = None
) -> dict[str, Any]:
    """Saját DB-rendelések aggregátuma — *order audit log* alapú."""
    total = (
        await session.execute(sa.select(sa.func.count()).select_from(Order))
    ).scalar_one()

    # Státusz szerinti bontás
    rows = (
        await session.execute(
            sa.select(Order.status, sa.func.count()).group_by(Order.status)
        )
    ).all()
    by_status: dict[str, int] = {s.value if hasattr(s, "value") else str(s): int(c) for s, c in rows}

    # Szimbólum szerinti top 10 (utolsó 30 nap, hogy ne a teljes history-t)
    since = datetime.now(UTC) - timedelta(days=30)
    sym_rows = (
        await session.execute(
            sa.select(Order.symbol, sa.func.count())
            .where(Order.created_at >= since)
            .group_by(Order.symbol)
            .order_by(sa.func.count().desc())
            .limit(10)
        )
    ).all()
    top_symbols = [{"symbol": s, "count": int(c)} for s, c in sym_rows if s]

    # Stratégia szerinti bontás (utolsó 30 nap)
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

    # Utolsó 24h aktivitás
    since_24h = datetime.now(UTC) - timedelta(hours=24)
    last_24h = (
        await session.execute(
            sa.select(sa.func.count())
            .select_from(Order)
            .where(Order.created_at >= since_24h)
        )
    ).scalar_one()

    in_window: int | None = None
    if lookback_hours is not None:
        since_win = datetime.now(UTC) - timedelta(hours=lookback_hours)
        in_window = (
            await session.execute(
                sa.select(sa.func.count())
                .select_from(Order)
                .where(Order.created_at >= since_win)
            )
        ).scalar_one()

    return {
        "total": int(total),
        "last_24h": int(last_24h),
        "in_lookback_window": int(in_window) if in_window is not None else None,
        "by_status": by_status,
        "top_symbols_30d": top_symbols,
        "by_strategy_30d": by_strategy,
    }


async def _events_summary(
    session: AsyncSession, *, lookback_hours: int = 24
) -> dict[str, Any]:
    """Audit eseménynapló aggregátum."""
    since_24h = datetime.now(UTC) - timedelta(hours=max(1, lookback_hours))
    total_24h = (
        await session.execute(
            sa.select(sa.func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.created_at >= since_24h)
        )
    ).scalar_one()
    rows = (
        await session.execute(
            sa.select(AuditEvent.level, sa.func.count())
            .where(AuditEvent.created_at >= since_24h)
            .group_by(AuditEvent.level)
        )
    ).all()
    by_level: dict[str, int] = {
        (lv.value if hasattr(lv, "value") else str(lv)): int(c) for lv, c in rows
    }

    # Legutóbbi 8 esemény (mini-feed)
    recent_rows = (
        await session.execute(
            sa.select(AuditEvent)
            .order_by(AuditEvent.created_at.desc())
            .limit(8)
        )
    ).scalars().all()
    recent = [
        {
            "id": e.id,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "level": e.level.value if e.level else None,
            "event": e.event,
            "message": e.message,
            "strategy_name": e.strategy_name,
        }
        for e in recent_rows
    ]

    # Utolsó ERROR esemény idő-átfutása
    last_error = (
        await session.execute(
            sa.select(AuditEvent.created_at)
            .where(AuditEvent.level == AuditLevel.ERROR)
            .order_by(AuditEvent.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    return {
        "total_24h": int(total_24h),
        "by_level_24h": by_level,
        "recent": recent,
        "last_error_at": last_error.isoformat() if last_error else None,
    }


async def _strategy_summary(
    session: AsyncSession, *, lookback_hours: int = 24
) -> dict[str, Any]:
    """Stratégia futások aggregátum + utolsó kalibráció."""
    since_24h = datetime.now(UTC) - timedelta(hours=max(1, lookback_hours))
    rows = (
        await session.execute(
            sa.select(StrategyRun.status, sa.func.count())
            .where(StrategyRun.started_at >= since_24h)
            .group_by(StrategyRun.status)
        )
    ).all()
    by_status: dict[str, int] = {
        (st.value if hasattr(st, "value") else str(st)): int(c) for st, c in rows
    }

    last_success = (
        await session.execute(
            sa.select(StrategyRun.started_at, StrategyRun.strategy_name)
            .where(StrategyRun.status == StrategyRunStatus.SUCCESS)
            .order_by(StrategyRun.started_at.desc())
            .limit(1)
        )
    ).first()
    last_failure = (
        await session.execute(
            sa.select(
                StrategyRun.started_at, StrategyRun.strategy_name, StrategyRun.error
            )
            .where(StrategyRun.status == StrategyRunStatus.FAILED)
            .order_by(StrategyRun.started_at.desc())
            .limit(1)
        )
    ).first()

    last_calib = (
        await session.execute(
            sa.select(TpSlCalibration)
            .order_by(TpSlCalibration.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    return {
        "by_status_24h": by_status,
        "last_success": (
            {
                "started_at": last_success[0].isoformat() if last_success[0] else None,
                "strategy_name": last_success[1],
            }
            if last_success
            else None
        ),
        "last_failure": (
            {
                "started_at": last_failure[0].isoformat() if last_failure[0] else None,
                "strategy_name": last_failure[1],
                "error": last_failure[2],
            }
            if last_failure
            else None
        ),
        "last_calibration": (
            {
                "status": last_calib.status.value if last_calib.status else None,
                "started_at": last_calib.started_at.isoformat()
                if last_calib.started_at
                else None,
                "finished_at": last_calib.finished_at.isoformat()
                if last_calib.finished_at
                else None,
            }
            if last_calib is not None
            else None
        ),
    }


def _extended_closed_kpis(realized_pnls: list[Decimal]) -> dict[str, Any]:
    wins = [v for v in realized_pnls if v > 0]
    losses = [v for v in realized_pnls if v < 0]
    gross_profit = sum(wins, Decimal(0))
    gross_loss_abs = abs(sum(losses, Decimal(0)))
    profit_factor: str | None = None
    if gross_loss_abs > 0:
        profit_factor = _q2(gross_profit / gross_loss_abs)
    total = len(realized_pnls)
    avg_win = gross_profit / Decimal(len(wins)) if wins else None
    avg_loss = sum(losses, Decimal(0)) / Decimal(len(losses)) if losses else None
    expectancy: str | None = None
    if total > 0 and avg_win is not None and avg_loss is not None:
        wr = Decimal(len(wins)) / Decimal(total)
        lr = Decimal(len(losses)) / Decimal(total)
        exp = avg_win * wr + avg_loss * lr
        expectancy = str(exp.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
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
        "profit_factor": profit_factor,
        "expectancy_usdt": expectancy,
        "max_drawdown_usdt": str(
            max_dd.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        ),
    }


async def _exchange_summary(
    client: BitunixClient,
    *,
    lookback_hours: int = 168,
    history_page_size: int = 100,
) -> dict[str, Any]:
    """Bitunix-szinkron: nyitott exposure + lezárt pozíciók KPI-jei.

    A ``get_history_positions`` szimbólum nélkül is hívható, akkor minden
    coint felölel — sokkal hatékonyabb, mint szimbólumonként végigmenni.
    Több oldalt is lehúzunk (``history_pages`` × ``history_page_size``), hogy
    a 7-30 napos visszatekintés alá elég adat kerüljön.
    """
    sync_error: str | None = None

    # 1) Számlaegyenleg (kis válasz, gyors)
    account: dict[str, Any] | None = None
    try:
        raw_acc = await client.get_account()
        data = raw_acc.get("data") if isinstance(raw_acc, dict) else None
        if isinstance(data, dict):
            account = {
                "margin_coin": data.get("marginCoin"),
                "available": data.get("available"),
                "margin": data.get("margin"),
                "frozen": data.get("frozen"),
                "transfer": data.get("transfer"),
                "cross_unrealized_pnl": data.get("crossUnrealizedPNL"),
                "isolation_unrealized_pnl": data.get("isolationUnrealizedPNL"),
                "bonus": data.get("bonus"),
                "position_mode": data.get("positionMode"),
            }
    except (BitunixAPIError, BitunixSignatureError) as exc:
        sync_error = f"Account: {exc}"[:500]

    # 2) Nyitott pozíciók
    open_positions: list[dict[str, Any]] = []
    try:
        raw_open = await client.get_positions()
        open_positions = [
            normalize_position_row(r) for r in extract_open_position_rows(raw_open)
        ]
    except (BitunixAPIError, BitunixSignatureError) as exc:
        msg = f"Nyitott pozíciók: {exc}"[:300]
        sync_error = msg if sync_error is None else f"{sync_error}; {msg}"

    total_unrealized = sum(
        (Decimal(p["unrealized_pnl"]) for p in open_positions if p["unrealized_pnl"]),
        Decimal(0),
    )
    total_margin = sum(
        (Decimal(p["margin"]) for p in open_positions if p["margin"]),
        Decimal(0),
    )

    # 3) Lezárt pozíciók — Bitunix history + szigorú ablakszűrés
    try:
        closed_positions, hist_err = await fetch_closed_positions_in_lookback(
            client,
            lookback_hours=lookback_hours,
            history_page_size=history_page_size,
        )
        if hist_err:
            msg = f"History pozíciók: {hist_err}"[:300]
            sync_error = msg if sync_error is None else f"{sync_error}; {msg}"
    except (BitunixAPIError, BitunixSignatureError) as exc:
        closed_positions = []
        msg = f"History pozíciók: {exc}"[:300]
        sync_error = msg if sync_error is None else f"{sync_error}; {msg}"

    realized_pnls = [
        Decimal(p["realized_pnl"])
        for p in closed_positions
        if p["realized_pnl"] is not None
    ]
    realized_sum = sum(realized_pnls, Decimal(0))
    wins = sum(1 for v in realized_pnls if v > 0)
    losses = sum(1 for v in realized_pnls if v < 0)
    total_closed = len(realized_pnls)
    win_rate = (
        (Decimal(wins) / Decimal(total_closed) * 100) if total_closed > 0 else None
    )
    avg_win = (
        sum((v for v in realized_pnls if v > 0), Decimal(0)) / Decimal(wins)
        if wins > 0
        else None
    )
    avg_loss = (
        sum((v for v in realized_pnls if v < 0), Decimal(0)) / Decimal(losses)
        if losses > 0
        else None
    )

    # Top winners / losers (lezárt pozíciók)
    sorted_closed = sorted(
        (p for p in closed_positions if p["realized_pnl"] is not None),
        key=lambda p: Decimal(p["realized_pnl"]),
        reverse=True,
    )
    top_winners = sorted_closed[:5]
    top_losers = sorted_closed[-5:][::-1]

    # Szimbólumonkénti realized PnL (lezárt pozíciók aggregátuma)
    per_symbol: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    for p in closed_positions:
        if p.get("symbol") and p.get("realized_pnl") is not None:
            per_symbol[p["symbol"]] += Decimal(p["realized_pnl"])
    per_symbol_list = sorted(
        ({"symbol": s, "realized_pnl_usdt": str(v)} for s, v in per_symbol.items()),
        key=lambda r: Decimal(r["realized_pnl_usdt"]),
        reverse=True,
    )
    extended = _extended_closed_kpis(realized_pnls)
    lookback_days_equiv = max(1, lookback_hours // 24)

    return {
        "sync_error": sync_error,
        "account": account,
        "open_positions": {
            "count": len(open_positions),
            "total_unrealized_pnl_usdt": str(total_unrealized),
            "total_margin_usdt": str(total_margin),
            "items": open_positions,
        },
        "closed_positions": {
            "lookback_hours": lookback_hours,
            "lookback_days": lookback_days_equiv,
            "count": total_closed,
            "realized_pnl_usdt": str(realized_sum),
            "win_rate_pct": _q2(win_rate) if win_rate is not None else None,
            "wins": wins,
            "losses": losses,
            "avg_win_usdt": str(avg_win) if avg_win is not None else None,
            "avg_loss_usdt": str(avg_loss) if avg_loss is not None else None,
            "profit_factor": extended["profit_factor"],
            "expectancy_usdt": extended["expectancy_usdt"],
            "max_drawdown_usdt": extended["max_drawdown_usdt"],
            "top_winners": top_winners,
            "top_losers": top_losers,
            "per_symbol": per_symbol_list,
        },
    }


async def build_dashboard_summary(
    session: AsyncSession,
    client: BitunixClient | None,
    *,
    lookback_hours: int = 168,
) -> dict[str, Any]:
    """Egyetlen aggregátum a frontend dashboardhoz."""
    db_orders = await _orders_summary(session, lookback_hours=lookback_hours)
    events = await _events_summary(session, lookback_hours=lookback_hours)
    strat = await _strategy_summary(session, lookback_hours=lookback_hours)
    exchange: dict[str, Any] = {
        "sync_error": (
            "Bitunix API kulcs hiányzik — nincs tőzsdei szinkron."
            if client is None
            else None
        ),
        "account": None,
        "open_positions": {
            "count": 0,
            "total_unrealized_pnl_usdt": "0",
            "total_margin_usdt": "0",
            "items": [],
        },
        "closed_positions": {
            "lookback_hours": lookback_hours,
            "lookback_days": max(1, lookback_hours // 24),
            "count": 0,
            "realized_pnl_usdt": "0",
            "win_rate_pct": None,
            "wins": 0,
            "losses": 0,
            "avg_win_usdt": None,
            "avg_loss_usdt": None,
            "profit_factor": None,
            "expectancy_usdt": None,
            "max_drawdown_usdt": "0",
            "top_winners": [],
            "top_losers": [],
            "per_symbol": [],
        },
    }
    if client is not None:
        exchange = await _exchange_summary(client, lookback_hours=lookback_hours)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "lookback_hours": lookback_hours,
        "lookback_days": max(1, lookback_hours // 24),
        "orders": db_orders,
        "events": events,
        "strategy": strat,
        "exchange": exchange,
    }
