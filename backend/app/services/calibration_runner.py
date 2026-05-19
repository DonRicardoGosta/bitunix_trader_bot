"""Kalibrációs scheduler és perzisztens állapot lekérdezése.

A ``CalibrationRunner`` minden óra **:30**-kor indul (ha van szabad slot),
és annyi jelöltet keres, amennyi pozícióhely üres (max. a stratégia
``count`` értéke).
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.bitunix.client import BitunixClient
from app.config import get_settings
from app.services.bitunix_client_factory import create_bitunix_client
from app.db import audit
from app.db.models import (
    AuditLevel,
    CalibrationStatus,
    TpSlCalibration,
)
from app.db.session import AsyncSessionLocal
from app.services.calibration import (
    CalibrationResult,
    CalibrationService,
    load_result_from_summary,
)
from app.services.candidate_backtest import BACKTEST_LOOKBACK_DAYS
from app.services.live_bus import DEFAULT_INVALIDATION_TOPICS, publish_invalidate
from app.services.strategy_runtime_config import get_top_signal_entries_config


def seconds_until_next_half_hour(now: datetime | None = None) -> float:
    """Másodperc a következő óra :30 percéig (UTC)."""
    now = now or datetime.now(UTC)
    target = now.replace(minute=30, second=0, microsecond=0)
    if now.minute > 30 or (now.minute == 30 and now.second > 0):
        target += timedelta(hours=1)
    elif now.minute < 30:
        pass
    elif now.second == 0 and now.microsecond == 0:
        return 0.0
    delta = (target - now).total_seconds()
    return max(0.0, delta)


async def count_open_strategy_slots(
    client: BitunixClient,
    *,
    target_slots: int,
) -> tuple[int, int]:
    """``(nyitott_pozíciók, kitöltendő_slot)``."""
    from app.services.strategy.mover_ranking import parse_open_position_symbols

    try:
        pos_raw = await client.get_positions()
        open_syms = parse_open_position_symbols(pos_raw)
    except Exception:  # noqa: BLE001
        open_syms = set()
    total_open = len(open_syms)
    need = max(0, target_slots - total_open)
    return total_open, need


async def _build_service(
    client: BitunixClient,
    session: AsyncSession,
    *,
    candidates_target: int,
    scan_limit: int,
) -> CalibrationService:
    lookback_minutes = BACKTEST_LOOKBACK_DAYS * 24 * 60
    return CalibrationService(
        client=client,
        lookback_minutes=lookback_minutes,
        top_n=scan_limit,
        candidates_target=candidates_target,
        kline_interval="15m",
        wf_choppiness_max=Decimal(
            (await get_top_signal_entries_config(session)).wf_choppiness_max
        ),
    )


async def run_calibration(
    *,
    triggered_by: str = "scheduler",
    candidates_target: int | None = None,
    scan_limit: int | None = None,
) -> dict[str, object]:
    """Egy teljes jelölt-kalibrációs futás (új ``TpSlCalibration`` rekord)."""
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        tse_cfg = await get_top_signal_entries_config(session)
        target_slots = max(1, int(tse_cfg.count))
        scan = scan_limit if scan_limit is not None else int(tse_cfg.scan_limit)

        if candidates_target is None:
            client_probe = await create_bitunix_client(session, settings=settings)
            try:
                _open, need = await count_open_strategy_slots(
                    client_probe, target_slots=target_slots
                )
                candidates_target = need
            finally:
                await client_probe.close()

    lookback_minutes = BACKTEST_LOOKBACK_DAYS * 24 * 60
    async with AsyncSessionLocal() as session:
        row = TpSlCalibration(
            status=CalibrationStatus.RUNNING,
            triggered_by=triggered_by,
            lookback_minutes=lookback_minutes,
            top_n=scan,
        )
        session.add(row)
        await session.flush()
        row_id = row.id
        await session.commit()

    if candidates_target is not None and candidates_target <= 0:
        async with AsyncSessionLocal() as session:
            db_row = await session.get(TpSlCalibration, row_id)
            if db_row is not None:
                db_row.finished_at = datetime.now(UTC)
                db_row.status = CalibrationStatus.SUCCESS
                db_row.summary = {
                    "mode": "candidate_backtest",
                    "candidates_target": 0,
                    "candidates_found": 0,
                    "skipped_reason": "slots_full",
                }
                await session.commit()
        await publish_invalidate(DEFAULT_INVALIDATION_TOPICS)
        return {
            "calibration_id": row_id,
            "status": CalibrationStatus.SUCCESS.value,
            "skipped": True,
            "reason": "slots_full",
        }

    error: str | None = None
    result: CalibrationResult | None = None
    async with AsyncSessionLocal() as session:
        client = await create_bitunix_client(session, settings=settings)
        try:
            service = await _build_service(
                client,
                session,
                candidates_target=int(candidates_target or 0),
                scan_limit=scan,
            )
            result = await service.run()
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
        finally:
            await client.close()

    out: dict[str, object]
    async with AsyncSessionLocal() as session:
        db_row = await session.get(TpSlCalibration, row_id)
        if db_row is not None:
            db_row.finished_at = datetime.now(UTC)
            if error:
                db_row.status = CalibrationStatus.FAILED
                db_row.error = error
            elif result is None:
                db_row.status = CalibrationStatus.FAILED
                db_row.error = "no_result"
            else:
                db_row.status = CalibrationStatus.SUCCESS
                db_row.summary = result.to_dict()
            await audit.record(
                session,
                f"calibration.{db_row.status.value.lower()}",
                level=AuditLevel.ERROR
                if db_row.status == CalibrationStatus.FAILED
                else AuditLevel.INFO,
                message=(
                    f"Kalibráció {db_row.status.value} (triggered_by={triggered_by}, "
                    f"jelöltek={result.candidates_found if result else 0}/"
                    f"{result.candidates_target if result else 0})."
                ),
                payload={
                    "calibration_id": row_id,
                    "status": db_row.status.value,
                    "candidates_target": (
                        result.candidates_target if result else None
                    ),
                    "candidates_found": (
                        result.candidates_found if result else None
                    ),
                    "scanned_symbols": result.scanned_symbols if result else None,
                    "error": db_row.error,
                },
            )
            await session.commit()
            out = {
                "calibration_id": row_id,
                "status": db_row.status.value,
                "error": db_row.error,
                "summary": db_row.summary,
            }
        else:
            out = {"calibration_id": row_id, "status": "UNKNOWN", "error": error}
    await publish_invalidate(DEFAULT_INVALIDATION_TOPICS)
    return out


async def get_latest_successful_calibration(
    session: AsyncSession,
    *,
    max_age_minutes: int | None = None,
) -> TpSlCalibration | None:
    """A legutóbbi SIKERES kalibráció lekérdezése."""
    stmt = (
        sa.select(TpSlCalibration)
        .where(TpSlCalibration.status == CalibrationStatus.SUCCESS)
        .order_by(TpSlCalibration.finished_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    row: TpSlCalibration | None = result.scalar_one_or_none()
    if row is None:
        return None
    if max_age_minutes is None:
        return row
    finished = row.finished_at
    if finished is None:
        return None
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=UTC)
    if datetime.now(UTC) - finished > timedelta(minutes=max_age_minutes):
        return None
    return row


async def get_active_calibration_result(
    session: AsyncSession,
) -> CalibrationResult | None:
    """A trading szempontjából aktív kalibráció betöltve."""
    settings = get_settings()
    max_age = max(
        settings.calibration_interval_seconds * 2 // 60,
        settings.calibration_max_age_minutes,
    )
    row = await get_latest_successful_calibration(session, max_age_minutes=max_age)
    if row is None or not row.summary:
        return None
    return load_result_from_summary(row.summary)


class CalibrationRunner:
    """Asyncio scheduler: minden óra :30-kor, ha van szabad pozícióslot."""

    def __init__(self, *, interval_seconds: int = 3600) -> None:
        self._interval = max(60, int(interval_seconds))
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._initial_done = asyncio.Event()

    @property
    def initial_run_complete(self) -> bool:
        return self._initial_done.is_set()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._initial_done.clear()
        self._task = asyncio.create_task(self._loop(), name="calibration-runner")
        await audit.record_isolated(
            "calibration.runner.started",
            message="Kalibrációs scheduler elindítva (óra :30, szabad slot).",
            payload={"schedule": "hourly_at_minute_30"},
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=self._interval + 5)
            except TimeoutError:
                self._task.cancel()
        await audit.record_isolated(
            "calibration.runner.stopped",
            message="Kalibrációs scheduler leállítva.",
        )

    async def wait_initial(self, timeout_seconds: float | None = None) -> bool:
        try:
            await asyncio.wait_for(self._initial_done.wait(), timeout=timeout_seconds)
            return True
        except TimeoutError:
            return False

    async def _loop(self) -> None:
        try:
            while not self._stop.is_set():
                wait_s = seconds_until_next_half_hour()
                if wait_s > 0:
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(self._stop.wait(), timeout=wait_s)
                    if self._stop.is_set():
                        break
                try:
                    await run_calibration(triggered_by="scheduler")
                except Exception as exc:  # noqa: BLE001
                    await audit.record_isolated(
                        "calibration.runner.iteration_error",
                        level=AuditLevel.ERROR,
                        message=f"Kalibrációs hiba: {exc}",
                    )
                finally:
                    self._initial_done.set()
                wait_next = seconds_until_next_half_hour()
                if wait_next > 0:
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(self._stop.wait(), timeout=wait_next)
        except asyncio.CancelledError:
            return
