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
    walk_forward_cooldown_minutes: int = Field(
        default=60,
        ge=0,
        le=10080,
        description="Virtuális trade lezárása után ennyi percet várunk a következő belépésig.",
    )

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


class WalkForwardAggregate(BaseModel):
    """Több időbeli vágási arány (≠ 0.5) ugyanazzal a szabálycsomaggal — összesítés."""

    model_config = ConfigDict(extra="forbid")

    total_runs: int = Field(ge=0)
    tp_first_count: int = Field(ge=0)
    sl_first_count: int = Field(ge=0)
    no_touch_count: int = Field(ge=0)
    direction_correct_count: int = Field(ge=0)
    strategy_win_rate_pct: str | None = None
    direction_hit_rate_pct: str | None = None


class WalkForwardTradeRow(BaseModel):
    """Egy szekvenciális virtuális trade (rész-chart indexek a teljes candles listához)."""

    model_config = ConfigDict(extra="forbid")

    trade_index: int = Field(ge=0)
    entry_bar_index: int = Field(ge=0)
    exit_bar_index: int = Field(ge=0)
    chart_from_index: int = Field(ge=0)
    chart_to_index: int = Field(ge=0)
    entry_time_ms: int
    exit_time_ms: int
    predicted_side: Literal["long", "short"]
    prediction_reason: str
    first_touch: Literal["tp", "sl", "none"]
    entry_price: str
    exit_price: str
    tp_price: str
    sl_price: str
    median_move_pct_train: str
    tp_move_pct: str
    sl_move_pct: str
    strategy_would_win: bool
    same_bar_ambiguous: bool
    direction_guess_correct: bool


class WalkForwardSequenceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_trades: int = Field(ge=0)
    tp_wins: int = Field(ge=0)
    sl_losses: int = Field(ge=0)
    no_result: int = Field(ge=0)
    direction_hits: int = Field(ge=0)


class WalkForwardCurrentSignal(BaseModel):
    """Utolsó gyertya zárójára: milyen irányt és TP/SL szinteket adna a modell most."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    disabled_reason: str | None = None
    predicted_side: Literal["long", "short"] | None = None
    prediction_reason: str | None = None
    entry_price: str | None = None
    tp_price: str | None = None
    sl_price: str | None = None
    median_move_pct_train: str | None = None
    tp_move_pct: str | None = None
    sl_move_pct: str | None = None
    train_bar_count: int = 0


class WalkForwardSequence(BaseModel):
    """50% első train után: trade → cooldown → új train (bővülő) → következő trade, stb."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    disabled_reason: str | None = None
    cooldown_minutes: int = 60
    initial_split_fraction: str = "0.5"
    first_checkpoint_time_ms: int | None = None
    tp_median_multiplier: str = "0.5"
    sl_median_multiplier: str = "0.5"
    trades: list[WalkForwardTradeRow] = Field(default_factory=list)
    summary: WalkForwardSequenceSummary | None = None
    current_signal: WalkForwardCurrentSignal


class WalkForwardSequenceCore(BaseModel):
    """Variációs sor: trade lista + összegzés (nincs ``current_signal``)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    disabled_reason: str | None = None
    cooldown_minutes: int = 60
    initial_split_fraction: str = "0.5"
    first_checkpoint_time_ms: int | None = None
    tp_median_multiplier: str
    sl_median_multiplier: str
    trades: list[WalkForwardTradeRow] = Field(default_factory=list)
    summary: WalkForwardSequenceSummary | None = None


class HoldWindowGridRow(BaseModel):
    """Egy tartási idő érték szimulációs eredménye."""

    model_config = ConfigDict(extra="forbid")

    hold_minutes: int = Field(ge=1)
    trades_evaluated: int = Field(ge=0)
    good_trades: int = Field(ge=0)
    good_rate_pct: str | None = None


class HoldWindowBlock(BaseModel):
    """Hold-window rács egy TP/SL variációhoz."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    profit_threshold_pct: str | None = None
    grid_minutes: list[int] = Field(default_factory=list)
    best_hold_minutes: int | None = None
    best_good_rate_pct: str | None = None
    rows: list[HoldWindowGridRow] = Field(default_factory=list)


class HoldWindowOptimizationInfo(BaseModel):
    """Stratégia config alapján: fut-e a hold optimalizálás az elemzésben."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    min_minutes: int = Field(default=30, ge=1)
    max_minutes: int = Field(default=60, ge=1)
    step_minutes: int = Field(default=5, ge=1)
    profit_threshold_pct: str = "15"


class TpslVariationRow(BaseModel):
    """Egy TP×medián / SL×medián kombináció eredménye."""

    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=0)
    tp_median_multiplier: str
    sl_median_multiplier: str
    label: str
    resolved_tp_win_rate_pct: str | None = None
    meets_target: bool = False
    resolved_count: int = Field(ge=0)
    trades_entered_last_48h_count: int = Field(ge=0)
    first_trade_tp_move_pct_raw: str | None = None
    first_trade_sl_move_pct_raw: str | None = None
    meets_min_tpsl_pct_profile: bool = False
    is_recommended: bool = False
    sequence: WalkForwardSequenceCore
    hold_window: HoldWindowBlock | None = None
    best_hold_minutes: int | None = None
    hold_good_rate_pct: str | None = None


class WalkForwardTpslVariations(BaseModel):
    """TP/SL variációk rácsa; cél: TP nyerési arány (feloldatlan trade nem számít sikernek)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    disabled_reason: str | None = None
    target_tp_win_rate_pct: str = "80"
    min_resolved_trades: int = Field(default=2, ge=1, le=100)
    any_variation_meets_target: bool = False
    has_recommended_variation: bool = False
    min_trades_last_48h_for_recommendation: int = Field(default=5, ge=1, le=100)
    lookback_hours: int = Field(default=48, ge=1, le=168)
    variation_tp_move_pct_min: str = Field(
        default="30",
        description="Ajánlási profil: első belépés nyers TP%% legalább ennyi (nem szimulációs klipp).",
    )
    variation_tp_move_pct_max: str = "300"
    variation_sl_move_pct_min: str = Field(
        default="10",
        description="Ajánlási profil: első belépés nyers SL%% legalább ennyi.",
    )
    variation_sl_move_pct_max: str = "150"
    best_current_signal: WalkForwardCurrentSignal | None = None
    variations: list[TpslVariationRow] = Field(default_factory=list)


class WalkForwardBacktest(BaseModel):
    """Félidős train → irány + medián/2 szimmetrikus TP/SL a hátsó fél gyertyáin."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    disabled_reason: str | None = None
    time_split_fraction: str | None = None
    train_start_time_ms: int | None = None
    train_end_time_ms: int | None = None
    checkpoint_time_ms: int | None = None
    test_start_time_ms: int | None = None
    test_end_time_ms: int | None = None
    train_bar_count: int = 0
    test_bar_count: int = 0
    median_move_pct_train: str | None = None
    tp_move_pct: str | None = None
    sl_move_pct: str | None = None
    entry_price: str | None = None
    tp_price: str | None = None
    sl_price: str | None = None
    test_start_close: str | None = None
    test_end_close: str | None = None
    predicted_side: Literal["long", "short"] | None = None
    prediction_reason: str | None = None
    test_net_move_pct: str | None = None
    actual_test_side: Literal["long", "short"] | None = None
    direction_guess_correct: bool | None = None
    first_touch: Literal["tp", "sl", "none"] | None = None
    first_touch_time_ms: int | None = None
    same_bar_ambiguous: bool | None = None
    strategy_would_win: bool | None = None
    aggregate: WalkForwardAggregate | None = None


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
    walk_forward_sequence: WalkForwardSequence
    walk_forward_tpsl_variations: WalkForwardTpslVariations
    hold_window_optimization: HoldWindowOptimizationInfo
