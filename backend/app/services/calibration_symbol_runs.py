"""Per-szimbólum kalibrációs backtest sorok DB-be írása és lekérdezése."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CalibrationStatus, TpSlCalibration, TpSlCalibrationSymbolRun
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


def _draft_to_row(calibration_id: int, draft: SymbolRunDraft) -> TpSlCalibrationSymbolRun:
    return TpSlCalibrationSymbolRun(
        calibration_id=calibration_id,
        symbol=draft.symbol,
        scan_rank=draft.scan_rank,
        abs_change_24h_pct=draft.abs_change_24h_pct,
        reason=draft.reason,
        is_qualified=draft.is_qualified,
        kline_samples=draft.kline_samples,
        best_variation_label=draft.best_variation_label,
        best_tp_roi_pct=draft.best_tp_roi_pct,
        best_sl_roi_pct=draft.best_sl_roi_pct,
        best_win_rate_pct=draft.best_win_rate_pct,
        max_win_rate_pct=draft.max_win_rate_pct,
        best_total_trades=draft.best_total_trades,
        best_tp_wins=draft.best_tp_wins,
        best_sl_losses=draft.best_sl_losses,
        best_no_result=draft.best_no_result,
        tp_move_pct=draft.tp_move_pct,
        sl_move_pct=draft.sl_move_pct,
        variations=draft.variations,
        fetch_error=draft.fetch_error,
    )


async def persist_symbol_run(
    session: AsyncSession,
    calibration_id: int,
    draft: SymbolRunDraft,
) -> None:
    """Egy coin scan eredmény azonnali mentése (flush, commit a hívóé)."""
    session.add(_draft_to_row(calibration_id, draft))
    await session.flush()


async def persist_symbol_run_committed(
    calibration_id: int,
    draft: SymbolRunDraft,
    *,
    scanned_symbols: int,
    candidates_found: int,
    candidates_target: int,
    top_n: int,
    publish_invalidate: bool = True,
) -> None:
    """Coin scan külön tranzakcióban + futás progress a parent rekordon."""
    from datetime import UTC, datetime

    from app.db.session import AsyncSessionLocal
    from app.services.live_bus import (
        DEFAULT_INVALIDATION_TOPICS,
        publish_invalidate as _publish,
    )

    async with AsyncSessionLocal() as session:
        await persist_symbol_run(session, calibration_id, draft)
        cal = await session.get(TpSlCalibration, calibration_id)
        if cal is not None and cal.status == CalibrationStatus.RUNNING:
            cal.summary = {
                "mode": "candidate_backtest",
                "in_progress": True,
                "scanned_symbols": scanned_symbols,
                "candidates_found": candidates_found,
                "candidates_target": candidates_target,
                "top_n": top_n,
                "symbol_runs_table": "tpsl_calibration_symbol_runs",
            }
        await session.commit()
    if publish_invalidate:
        await _publish(DEFAULT_INVALIDATION_TOPICS)


async def persist_symbol_runs(
    session: AsyncSession,
    calibration_id: int,
    drafts: list[SymbolRunDraft],
) -> int:
    """Több coin scan egyszerre (tesztek / legacy); élesben coinonként commit."""
    if not drafts:
        return 0
    session.add_all([_draft_to_row(calibration_id, d) for d in drafts])
    await session.flush()
    return len(drafts)


async def count_symbol_runs(
    session: AsyncSession,
    calibration_id: int,
) -> int:
    stmt = (
        sa.select(sa.func.count())
        .select_from(TpSlCalibrationSymbolRun)
        .where(TpSlCalibrationSymbolRun.calibration_id == calibration_id)
    )
    return int((await session.execute(stmt)).scalar_one())


def resolve_symbol_runs_calibration_id(
    latest_any: TpSlCalibration | None,
    latest_success: TpSlCalibration | None,
) -> int | None:
    """Melyik futás symbol-runjait mutassa a UI (soha nem kever két futást).

    - Futás közben (RUNNING): az aktuális futás ID-ja.
    - Egyébként: utolsó sikeres kalibráció (trading gate-del egyezik).
    """
    if latest_any is not None and latest_any.status == CalibrationStatus.RUNNING:
        return latest_any.id
    if latest_success is not None:
        return latest_success.id
    if latest_any is not None:
        return latest_any.id
    return None


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
    """Egy szimbólum utolsó N sikeres kalibrációs backtest sorai."""
    stmt = (
        sa.select(TpSlCalibrationSymbolRun)
        .join(
            TpSlCalibration,
            TpSlCalibration.id == TpSlCalibrationSymbolRun.calibration_id,
        )
        .where(
            TpSlCalibrationSymbolRun.symbol == symbol.upper(),
            TpSlCalibration.status == CalibrationStatus.SUCCESS,
        )
        .order_by(TpSlCalibrationSymbolRun.created_at.desc())
        .limit(max(1, min(limit, 100)))
    )
    return list((await session.execute(stmt)).scalars().all())
