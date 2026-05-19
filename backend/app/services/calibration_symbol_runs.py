"""Per-szimbólum kalibrációs backtest sorok DB-be írása és lekérdezése."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TpSlCalibrationSymbolRun
from app.services.tpsl import implied_price_move_pct_from_roi


def _decimal_or_none(value: str | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def max_variation_win_rate_pct(variations: list[dict[str, Any]] | None) -> Decimal | None:
    """A variációk közül a legmagasabb feloldott TP win rate (%)."""
    if not variations:
        return None
    rates: list[Decimal] = []
    for row in variations:
        raw = row.get("resolved_tp_win_rate_pct")
        if raw is None:
            continue
        rates.append(Decimal(str(raw)))
    if not rates:
        return None
    return max(rates)


@dataclass
class SymbolRunDraft:
    """Egy coin scan eredménye kalibráció közben (még nincs DB-ben)."""

    symbol: str
    scan_rank: int
    abs_change_24h_pct: Decimal
    reason: str
    is_qualified: bool
    kline_samples: int | None = None
    best_variation_label: str | None = None
    best_tp_roi_pct: Decimal | None = None
    best_sl_roi_pct: Decimal | None = None
    best_win_rate_pct: Decimal | None = None
    max_win_rate_pct: Decimal | None = None
    best_total_trades: int | None = None
    best_tp_wins: int | None = None
    best_sl_losses: int | None = None
    best_no_result: int | None = None
    tp_move_pct: Decimal | None = None
    sl_move_pct: Decimal | None = None
    variations: list[dict[str, Any]] | None = None
    fetch_error: str | None = None


def draft_from_fetch_failure(
    *,
    symbol: str,
    scan_rank: int,
    abs_change_24h_pct: Decimal,
    error: str,
) -> SymbolRunDraft:
    return SymbolRunDraft(
        symbol=symbol,
        scan_rank=scan_rank,
        abs_change_24h_pct=abs_change_24h_pct,
        reason="fetch_failed",
        is_qualified=False,
        fetch_error=error,
    )


def draft_from_evaluation(
    *,
    symbol: str,
    scan_rank: int,
    abs_change_24h_pct: Decimal,
    kline_samples: int,
    eval_out: dict[str, Any],
    is_selected_candidate: bool,
) -> SymbolRunDraft:
    """``evaluate_symbol_variations`` kimenetéből draft (qualified vagy elutasított)."""
    variations = list(eval_out.get("variations") or [])
    max_wr = max_variation_win_rate_pct(variations)
    reason = str(eval_out.get("reason", "not_qualified"))
    best = eval_out.get("best_variation")
    ok = bool(eval_out.get("ok") and best is not None)

    best_label: str | None = None
    best_tp: Decimal | None = None
    best_sl: Decimal | None = None
    best_wr: Decimal | None = None
    tp_move: Decimal | None = None
    sl_move: Decimal | None = None
    total = tp_w = sl_l = no_r = None

    if ok and best is not None:
        best_label = str(best.get("label", ""))
        best_tp = _decimal_or_none(best.get("tp_roi_pct"))
        best_sl = _decimal_or_none(best.get("sl_roi_pct"))
        best_wr = _decimal_or_none(best.get("resolved_tp_win_rate_pct"))
        summary = best.get("summary") or {}
        total = int(summary.get("total_trades", 0))
        tp_w = int(summary.get("tp_wins", 0))
        sl_l = int(summary.get("sl_losses", 0))
        no_r = int(summary.get("no_result", 0))
        if best_tp is not None and best_sl is not None:
            tp_move, sl_move = implied_price_move_pct_from_roi(
                leverage=20,
                tp_roi_pct=best_tp,
                sl_roi_pct=best_sl,
            )
        reason = "qualified" if is_selected_candidate else reason

    return SymbolRunDraft(
        symbol=symbol,
        scan_rank=scan_rank,
        abs_change_24h_pct=abs_change_24h_pct,
        reason=reason,
        is_qualified=is_selected_candidate,
        kline_samples=kline_samples,
        best_variation_label=best_label,
        best_tp_roi_pct=best_tp,
        best_sl_roi_pct=best_sl,
        best_win_rate_pct=best_wr,
        max_win_rate_pct=max_wr,
        best_total_trades=total,
        best_tp_wins=tp_w,
        best_sl_losses=sl_l,
        best_no_result=no_r,
        tp_move_pct=tp_move,
        sl_move_pct=sl_move,
        variations=variations,
    )


async def persist_symbol_runs(
    session: AsyncSession,
    calibration_id: int,
    drafts: list[SymbolRunDraft],
) -> int:
    """Összes coin scan bulk mentése; visszaadja a beszúrt sorok számát."""
    if not drafts:
        return 0
    rows = [
        TpSlCalibrationSymbolRun(
            calibration_id=calibration_id,
            symbol=d.symbol,
            scan_rank=d.scan_rank,
            abs_change_24h_pct=d.abs_change_24h_pct,
            reason=d.reason,
            is_qualified=d.is_qualified,
            kline_samples=d.kline_samples,
            best_variation_label=d.best_variation_label,
            best_tp_roi_pct=d.best_tp_roi_pct,
            best_sl_roi_pct=d.best_sl_roi_pct,
            best_win_rate_pct=d.best_win_rate_pct,
            max_win_rate_pct=d.max_win_rate_pct,
            best_total_trades=d.best_total_trades,
            best_tp_wins=d.best_tp_wins,
            best_sl_losses=d.best_sl_losses,
            best_no_result=d.best_no_result,
            tp_move_pct=d.tp_move_pct,
            sl_move_pct=d.sl_move_pct,
            variations=d.variations,
            fetch_error=d.fetch_error,
        )
        for d in drafts
    ]
    session.add_all(rows)
    await session.flush()
    return len(rows)


def symbol_run_to_dict(row: TpSlCalibrationSymbolRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "calibration_id": row.calibration_id,
        "symbol": row.symbol,
        "scan_rank": row.scan_rank,
        "abs_change_24h_pct": str(row.abs_change_24h_pct),
        "reason": row.reason,
        "is_qualified": row.is_qualified,
        "kline_samples": row.kline_samples,
        "best_variation_label": row.best_variation_label,
        "best_tp_roi_pct": (
            str(row.best_tp_roi_pct) if row.best_tp_roi_pct is not None else None
        ),
        "best_sl_roi_pct": (
            str(row.best_sl_roi_pct) if row.best_sl_roi_pct is not None else None
        ),
        "best_win_rate_pct": (
            str(row.best_win_rate_pct) if row.best_win_rate_pct is not None else None
        ),
        "max_win_rate_pct": (
            str(row.max_win_rate_pct) if row.max_win_rate_pct is not None else None
        ),
        "best_total_trades": row.best_total_trades,
        "best_tp_wins": row.best_tp_wins,
        "best_sl_losses": row.best_sl_losses,
        "best_no_result": row.best_no_result,
        "tp_move_pct": str(row.tp_move_pct) if row.tp_move_pct is not None else None,
        "sl_move_pct": str(row.sl_move_pct) if row.sl_move_pct is not None else None,
        "variations": row.variations,
        "fetch_error": row.fetch_error,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def list_symbol_runs_for_calibration(
    session: AsyncSession,
    calibration_id: int,
    *,
    symbol: str | None = None,
    qualified_only: bool | None = None,
    limit: int = 200,
    offset: int = 0,
    order_by: str = "scan_rank",
) -> tuple[list[TpSlCalibrationSymbolRun], int]:
    """Szűrt lista + teljes darabszám (lapozáshoz)."""
    base = sa.select(TpSlCalibrationSymbolRun).where(
        TpSlCalibrationSymbolRun.calibration_id == calibration_id
    )
    if symbol:
        base = base.where(TpSlCalibrationSymbolRun.symbol == symbol.upper())
    if qualified_only is True:
        base = base.where(TpSlCalibrationSymbolRun.is_qualified.is_(True))
    elif qualified_only is False:
        base = base.where(TpSlCalibrationSymbolRun.is_qualified.is_(False))

    count_stmt = sa.select(sa.func.count()).select_from(base.subquery())
    total = int((await session.execute(count_stmt)).scalar_one())

    if order_by == "max_win_rate":
        ordered = base.order_by(
            TpSlCalibrationSymbolRun.max_win_rate_pct.desc().nullslast(),
            TpSlCalibrationSymbolRun.scan_rank,
        )
    elif order_by == "best_win_rate":
        ordered = base.order_by(
            TpSlCalibrationSymbolRun.best_win_rate_pct.desc().nullslast(),
            TpSlCalibrationSymbolRun.scan_rank,
        )
    else:
        ordered = base.order_by(TpSlCalibrationSymbolRun.scan_rank)

    stmt = ordered.offset(max(0, offset)).limit(max(1, min(limit, 500)))
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows), total


async def list_symbol_history(
    session: AsyncSession,
    symbol: str,
    *,
    limit: int = 20,
) -> list[TpSlCalibrationSymbolRun]:
    """Egy szimbólum utolsó N kalibrációs backtest sorai (visszakövethetőség)."""
    stmt = (
        sa.select(TpSlCalibrationSymbolRun)
        .where(TpSlCalibrationSymbolRun.symbol == symbol.upper())
        .order_by(TpSlCalibrationSymbolRun.created_at.desc())
        .limit(max(1, min(limit, 100)))
    )
    return list((await session.execute(stmt)).scalars().all())
