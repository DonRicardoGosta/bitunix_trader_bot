"""Trading blackout API sémák."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.trading_blackout import DayBlackoutConfig, TradingBlackoutSchedule


class TradingBlackoutScheduleBody(TradingBlackoutSchedule):
    """PUT /api/settings/trading-blackout törzs."""


class DayBlackoutConfigPatch(DayBlackoutConfig):
    """Egy nap konfigurációja (frontend)."""


class TradingBlackoutStatus(BaseModel):
    new_position_open_allowed: bool
    block_reason: str | None = None
    schedule: dict = Field(default_factory=dict)
