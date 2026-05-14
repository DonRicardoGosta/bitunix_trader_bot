"""Coin elemzés API sémák."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MarketSymbolRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    max_leverage: int = Field(ge=1, le=500)


class CoinAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(..., min_length=3, max_length=32)
    lookback_minutes: int = Field(default=1440, ge=5, le=120960)  # max 12 hét

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, v: str) -> str:
        s = str(v).strip().upper()
        if len(s) < 3:
            raise ValueError("symbol túl rövid")
        return s


class CandleChartRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time_ms: int
    open: str
    high: str
    low: str
    close: str


class CleanLegRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_time_ms: int
    end_time_ms: int
    start_index: int = Field(ge=0)
    end_index: int = Field(ge=0)
    direction: Literal["up", "down"]
    move_pct: str
    choppiness: str
    start_price: str
    end_price: str


class CoinAnalyzeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    max_leverage: int
    interval: str
    kline_limit: int
    lookback_minutes_requested: int
    choppiness_max: str
    candles: list[CandleChartRow]
    clean_legs: list[CleanLegRow]
    median_move_pct: str | None
    mean_move_pct: str | None
    clean_leg_count: int
    all_leg_count: int
