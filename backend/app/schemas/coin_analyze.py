"""Coin elemzés API sémák."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MarketSymbolRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    max_leverage: int = Field(ge=1)


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


class WalkForwardBacktest(BaseModel):
    """Félidős train → irány + medián/2 szimmetrikus TP/SL a hátsó fél gyertyáin."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    disabled_reason: str | None = None
    checkpoint_time_ms: int | None = None
    train_bar_count: int = 0
    test_bar_count: int = 0
    median_move_pct_train: str | None = None
    tp_move_pct: str | None = None
    sl_move_pct: str | None = None
    entry_price: str | None = None
    predicted_side: Literal["long", "short"] | None = None
    prediction_reason: str | None = None
    test_net_move_pct: str | None = None
    actual_test_side: Literal["long", "short"] | None = None
    direction_guess_correct: bool | None = None
    first_touch: Literal["tp", "sl", "none"] | None = None
    first_touch_time_ms: int | None = None
    same_bar_ambiguous: bool | None = None
    strategy_would_win: bool | None = None


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
    walk_forward: WalkForwardBacktest
