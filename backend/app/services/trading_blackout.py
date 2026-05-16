"""Új pozíció nyitás tiltása — hét nap + idősávok (runtime DB)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppRuntimeSetting

RUNTIME_KEY = "trading_blackout_schedule"
_DEFAULT_TZ = "Europe/Budapest"

WEEKDAY_KEYS: tuple[str, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

WEEKDAY_LABELS_HU: dict[str, str] = {
    "monday": "Hétfő",
    "tuesday": "Kedd",
    "wednesday": "Szerda",
    "thursday": "Csütörtök",
    "friday": "Péntek",
    "saturday": "Szombat",
    "sunday": "Vasárnap",
}

_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


class BlackoutTimeRange(BaseModel):
    """Tiltott időszak egy napon (helyi idő, ``HH:MM``)."""

    start: str = Field(description="Kezdet, pl. 22:00")
    end: str = Field(description="Vég, pl. 06:00 (éjfél utáni is lehet)")

    @field_validator("start", "end")
    @classmethod
    def _validate_hhmm(cls, v: str) -> str:
        m = _TIME_RE.match(v.strip())
        if not m:
            raise ValueError("Időformátum: HH:MM")
        h, mi = int(m.group(1)), int(m.group(2))
        if h > 23 or mi > 59:
            raise ValueError("Érvénytelen óra vagy perc")
        return f"{h:02d}:{mi:02d}"


class DayBlackoutConfig(BaseModel):
    """Egy hét napjának tiltási beállítása."""

    mode: Literal["open", "block_all", "block_ranges"] = Field(
        default="open",
        description="open = nincs tiltás; block_all = egész nap; block_ranges = idősávok",
    )
    block_ranges: list[BlackoutTimeRange] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ranges_required_when_mode(self) -> DayBlackoutConfig:
        if self.mode == "block_ranges" and not self.block_ranges:
            raise ValueError("block_ranges kötelező, ha mode=block_ranges")
        if self.mode != "block_ranges" and self.block_ranges:
            raise ValueError("block_ranges csak block_ranges módban használható")
        return self


class TradingBlackoutSchedule(BaseModel):
    """Heti ütemezés: mikor NE nyisson új pozíciót."""

    timezone: str = Field(default=_DEFAULT_TZ)
    days: dict[str, DayBlackoutConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _ensure_all_days(self) -> TradingBlackoutSchedule:
        for key in WEEKDAY_KEYS:
            if key not in self.days:
                self.days[key] = DayBlackoutConfig()
        return self


def default_trading_blackout_schedule() -> dict[str, Any]:
    """Minden nap engedélyezett (nincs tiltás)."""
    return TradingBlackoutSchedule().model_dump()


def _parse_hhmm(value: str) -> int:
    """Perc éjféltől (0–1439)."""
    m = _TIME_RE.match(value)
    if not m:
        return 0
    return int(m.group(1)) * 60 + int(m.group(2))


def _minutes_in_blackout_range(now_min: int, start_min: int, end_min: int) -> bool:
    if start_min == end_min:
        return True
    if start_min < end_min:
        return start_min <= now_min < end_min
    return now_min >= start_min or now_min < end_min


def is_time_in_day_blackout(cfg: DayBlackoutConfig, now_min: int) -> bool:
    if cfg.mode == "open":
        return False
    if cfg.mode == "block_all":
        return True
    for r in cfg.block_ranges:
        if _minutes_in_blackout_range(now_min, _parse_hhmm(r.start), _parse_hhmm(r.end)):
            return True
    return False


def is_in_trading_blackout(schedule: TradingBlackoutSchedule, at: datetime) -> bool:
    """True, ha ``at`` időpontban tiltva van az új pozíció nyitás."""
    tz = ZoneInfo(schedule.timezone)
    local = at.astimezone(tz) if at.tzinfo else at.replace(tzinfo=UTC).astimezone(tz)
    weekday_idx = local.weekday()
    day_key = WEEKDAY_KEYS[weekday_idx]
    cfg = schedule.days.get(day_key) or DayBlackoutConfig()
    now_min = local.hour * 60 + local.minute
    return is_time_in_day_blackout(cfg, now_min)


def blackout_block_message(
    schedule: TradingBlackoutSchedule, at: datetime
) -> str | None:
    """Magyar hibaüzenet, ha tiltva van; egyébként None."""
    if not is_in_trading_blackout(schedule, at):
        return None
    tz = ZoneInfo(schedule.timezone)
    local = at.astimezone(tz) if at.tzinfo else at.replace(tzinfo=UTC).astimezone(tz)
    day_key = WEEKDAY_KEYS[local.weekday()]
    label = WEEKDAY_LABELS_HU[day_key]
    cfg = schedule.days.get(day_key) or DayBlackoutConfig()
    if cfg.mode == "block_all":
        return f"Új pozíció tiltva: {label} egész nap (ütemezés)."
    if cfg.mode == "block_ranges":
        ranges = ", ".join(f"{r.start}–{r.end}" for r in cfg.block_ranges)
        return f"Új pozíció tiltva: {label} {ranges} között (ütemezés)."
    return "Új pozíció tiltva az ütemezés szerint."


async def get_trading_blackout_schedule(session: AsyncSession) -> dict[str, Any]:
    row = await session.get(AppRuntimeSetting, RUNTIME_KEY)
    if row is None:
        return default_trading_blackout_schedule()
    try:
        raw = json.loads(row.value)
    except json.JSONDecodeError:
        return default_trading_blackout_schedule()
    try:
        return TradingBlackoutSchedule.model_validate(raw).model_dump()
    except Exception:
        return default_trading_blackout_schedule()


async def set_trading_blackout_schedule(
    session: AsyncSession, data: dict[str, Any]
) -> dict[str, Any]:
    """Validál és menti a hetit."""
    schedule = TradingBlackoutSchedule.model_validate(data)
    encoded = schedule.model_dump_json()
    existing = await session.get(AppRuntimeSetting, RUNTIME_KEY)
    if existing is None:
        session.add(AppRuntimeSetting(key=RUNTIME_KEY, value=encoded))
    else:
        existing.value = encoded
        existing.updated_at = datetime.now(UTC)
    return schedule.model_dump()


async def is_new_position_open_blocked(
    session: AsyncSession, *, at: datetime | None = None
) -> tuple[bool, str | None]:
    """(tiltva, üzenet) — csak új pozíció nyitásra."""
    raw = await get_trading_blackout_schedule(session)
    schedule = TradingBlackoutSchedule.model_validate(raw)
    moment = at or datetime.now(UTC)
    if not is_in_trading_blackout(schedule, moment):
        return False, None
    return True, blackout_block_message(schedule, moment)
