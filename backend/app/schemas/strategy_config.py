"""Top signal entries stratégia runtime konfig (DB, nem env)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TopSignalEntriesConfig(BaseModel):
    """Effektív stratégia paraméterek — alapértelmezés kódban, felülírás DB-ben."""

    count: int = Field(ge=1, le=100, default=10)
    scan_limit_max: int = Field(ge=1, le=5000, default=200)
    scan_limit: int = Field(ge=1, le=5000, default=200)
    kline_lookahead: int = Field(ge=1, le=5000, default=200)
    kline_interval: str = "15m"
    kline_limit: int = Field(ge=3, le=500, default=80)
    cooldown_minutes: int = Field(ge=0, le=10080, default=240)
    min_abs_change_pct: str = "1.0"
    range_threshold: str = "0.60"
    max_kline_concurrency: int = Field(ge=1, le=50, default=10)
    wf_gate_enabled: bool = True
    wf_lookback_minutes: int = Field(ge=60, le=20160, default=4320)
    wf_cooldown_minutes: int = Field(ge=0, le=10080, default=60)
    wf_choppiness_max: str = "1.72"
    margin_pct_of_balance: str = "0.01"
    min_margin_usdt: str = "0.2"
    tp_roi_pct: str = "200"
    sl_roi_pct: str = "100"
    min_tp_roi_pct: str = "60"
    tpsl_stop_type: Literal["MARK_PRICE", "LAST_PRICE"] = "MARK_PRICE"
    hold_window_optimization_enabled: bool = False
    hold_window_min_minutes: int = Field(ge=5, le=240, default=30)
    hold_window_max_minutes: int = Field(ge=5, le=480, default=60)
    hold_window_step_minutes: int = Field(ge=1, le=60, default=5)
    hold_profit_threshold_pct: str = "15"


class TopSignalEntriesConfigPatch(BaseModel):
    """Részleges frissítés — csak a megadott mezők változnak."""

    count: int | None = Field(default=None, ge=1, le=100)
    scan_limit_max: int | None = Field(default=None, ge=1, le=5000)
    scan_limit: int | None = Field(default=None, ge=1, le=5000)
    kline_lookahead: int | None = Field(default=None, ge=1, le=5000)
    kline_interval: str | None = None
    kline_limit: int | None = Field(default=None, ge=3, le=500)
    cooldown_minutes: int | None = Field(default=None, ge=0, le=10080)
    min_abs_change_pct: str | None = None
    range_threshold: str | None = None
    max_kline_concurrency: int | None = Field(default=None, ge=1, le=50)
    wf_gate_enabled: bool | None = None
    wf_lookback_minutes: int | None = Field(default=None, ge=60, le=20160)
    wf_cooldown_minutes: int | None = Field(default=None, ge=0, le=10080)
    wf_choppiness_max: str | None = None
    margin_pct_of_balance: str | None = None
    min_margin_usdt: str | None = None
    tp_roi_pct: str | None = None
    sl_roi_pct: str | None = None
    min_tp_roi_pct: str | None = None
    tpsl_stop_type: Literal["MARK_PRICE", "LAST_PRICE"] | None = None
    hold_window_optimization_enabled: bool | None = None
    hold_window_min_minutes: int | None = Field(default=None, ge=5, le=240)
    hold_window_max_minutes: int | None = Field(default=None, ge=5, le=480)
    hold_window_step_minutes: int | None = Field(default=None, ge=1, le=60)
    hold_profit_threshold_pct: str | None = None
