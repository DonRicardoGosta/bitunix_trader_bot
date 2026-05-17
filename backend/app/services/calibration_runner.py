"""Kalibrációs scheduler és perzisztens állapot lekérdezése.

Két felelősség:
1. ``CalibrationRunner`` – asyncio task, ami az induláskor egyszer lefuttatja
   a kalibrációt, majd óránként (vagy a beállított intervallumban) ismét.
2. ``get_latest_successful_calibration()`` – a stratégia és az API ezen
   keresztül nézi meg, hogy van-e érvényes kalibráció. A "trading
   engedélyezett" állapot ennek a függvénynek a kimenetén áll vagy bukik.
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
from app.services.live_bus import DEFAULT_INVALIDATION_TOPICS, publish_invalidate


def _build_service(client: BitunixClient) -> CalibrationService:
    settings = get_settings()
    return CalibrationService(
        client=client,
        lookback_minutes=settings.calibration_lookback_minutes,
        top_n=settings.calibration_top_n,
        tp_atr_mult=Decimal(settings.calibration_tp_atr_mult),
        sl_atr_mult=Decimal(settings.calibration_sl_atr_mult),
        kline_interval=settings.calibration_kline_interval,
    )


async def run_calibration(*, triggered_by: str = "scheduler") -> dict[str, object]:
    """Egy teljes kalibrációs futás (új ``TpSlCalibration`` rekord)."""
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        row = TpSlCalibration(
            status=CalibrationStatus.RUNNING,
            triggered_by=triggered_by,
            lookback_minutes=settings.calibration_lookback_minutes,
            top_n=settings.calibration_top_n,
        )
        session.add(row)
        await session.flush()
        row_id = row.id
        await session.commit()

    async with AsyncSessionLocal() as session:
        client = await create_bitunix_client(session, settings=settings)

    error: str | None = None
    result: CalibrationResult | None = None
    try:
        service = _build_service(client)
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
            elif result is None or not result.per_symbol:
                db_row.status = CalibrationStatus.FAILED
                db_row.error = "no_symbols_calibrated"
                if result is not None:
                    db_row.summary = result.to_dict()
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
                    f"Kalibráció {db_row.status.value} (triggered_by={triggered_by})."
                ),
                payload={
                    "calibration_id": row_id,
                    "status": db_row.status.value,
                    "lookback_minutes": db_row.lookback_minutes,
                    "top_n": db_row.top_n,
                    "calibrated_symbols": (len(result.per_symbol) if result else 0),
                    "failed_symbols": (len(result.failed_symbols) if result else 0),
                    "global": (result.to_dict()["global"] if result else None),
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
    """A legutóbbi SIKERES kalibráció lekérdezése.

    Ha ``max_age_minutes`` meg van adva, akkor csak akkor adja vissza,
    ha a finished_at fiatalabb a megadott küszöbnél.
    """
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
    """A trading szempontjából 'aktív' kalibráció betöltve in-memory DTO-ba.

    A "max age" alapból = ``calibration_interval_seconds × 2`` (1h-ás futásnál
    = 2h). Ezzel akkor sem trade-elünk vakon, ha a scheduler valamiért
    megakadt.
    """
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
    """Asyncio scheduler ami az induláskor és aztán óránként kalibrál."""

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
            message=f"Kalibrációs scheduler elindítva ({self._interval}s).",
            payload={"interval_seconds": self._interval},
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
        """Blokkol amíg az első futás be nem fejeződik (vagy timeout)."""
        try:
            await asyncio.wait_for(self._initial_done.wait(), timeout=timeout_seconds)
            return True
        except TimeoutError:
            return False

    async def _loop(self) -> None:
        try:
            while not self._stop.is_set():
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
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
        except asyncio.CancelledError:
            return
