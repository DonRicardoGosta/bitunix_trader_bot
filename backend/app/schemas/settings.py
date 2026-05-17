"""Runtime settings API sémák."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RuntimeSettingsPatch(BaseModel):
    trading_paused: bool | None = None
    require_calibration_for_trading: bool | None = None
    strategy_runner_paused: bool | None = None
    bitunix_live_trading: bool | None = None
    strategy_top_signal_entries_enabled: bool | None = None


class TradingPauseBody(BaseModel):
    paused: bool = Field(description="True = minden order blokkolva")
