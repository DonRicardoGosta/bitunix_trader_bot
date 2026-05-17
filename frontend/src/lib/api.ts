/**
 * Backend API kliens. Soha NEM beszél közvetlenül a Bitunix-szal;
 * mindent a saját FastAPI backendünkön keresztül routol.
 */

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://localhost:8000";

/** Tesztekhez és egyértelmű URL-építéshez (http/https → ws/wss). */
export function toLiveStreamWsUrl(apiBaseHttp: string): string {
  const base = apiBaseHttp.replace(/\/+$/, "");
  const u = new URL("/api/live/stream", base.endsWith("/") ? base : `${base}/`);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  return u.toString();
}

/** WebSocket URL a backend ``/api/live/stream`` végpontjához (http→ws). */
export function liveStreamWebSocketUrl(): string {
  return toLiveStreamWsUrl(BASE_URL);
}

export interface TickerInfo {
  symbol: string;
  last_price: string;
  high_24h?: string | null;
  low_24h?: string | null;
  volume_24h?: string | null;
}

export interface OrderExchangeInfo {
  synced: boolean;
  sync_error: string | null;
  order_status: string | null;
  lifecycle: string;
  lifecycle_label: string;
  realized_pnl_usdt: string | null;
  /** Csak nyitott pozíción jön vissza (mark-to-market). */
  unrealized_pnl_usdt: string | null;
  roi_pct: string | null;
  margin_usdt_estimate: string | null;
  /** Bitunix pozíció ID, ha sikerült párosítani a rendeléshez. */
  position_id: string | null;
  /** Csak GET /api/orders?debug_sync=1 esetén – hibakereséshez */
  debug?: Record<string, unknown>;
}

export interface OrderWalkForwardContext {
  gate_source?: string | null;
  prediction_reason?: string | null;
  target_tp_win_rate_pct?: string | null;
  variation?: {
    rank?: number;
    label?: string | null;
    resolved_tp_win_rate_pct?: string | number | null;
    meets_target?: boolean;
    meets_min_tpsl_pct_profile?: boolean;
    trades_entered_last_48h_count?: number;
    resolved_count?: number;
    tp_median_multiplier?: string | number | null;
    sl_median_multiplier?: string | number | null;
    target_tp_win_rate_pct?: string | null;
  } | null;
}

export interface OrderEntryContext {
  strategy?: string;
  signal_reason?: string;
  direction_reason?: string;
  change_pct_24h?: string;
  range_position?: string | null;
  tp_source?: string;
  tp_move_pct?: string;
  sl_move_pct?: string;
  walk_forward?: OrderWalkForwardContext | null;
}

export interface OrderRow {
  id: number;
  client_order_id: string;
  bitunix_order_id: string | null;
  symbol: string;
  side: "BUY" | "SELL";
  type: "MARKET" | "LIMIT";
  quantity: string;
  price: string | null;
  leverage: number;
  status: string;
  created_at: string;
  exchange: OrderExchangeInfo;
  /** Stratégia-belépés összefoglaló (WF win rate, forrás stb.). */
  entry_context?: OrderEntryContext | null;
}

/** GET /api/orders/pnl-totals — összes saját DB rendelés PnL összesítője */
export interface OrdersPnlTotals {
  lookback_hours?: number;
  order_count: number;
  realized_pnl_usdt: string;
  unrealized_pnl_usdt: string;
  total_pnl_usdt: string;
  sync_error: string | null;
}

export interface PlaceOrderInput {
  symbol: string;
  side: "BUY" | "SELL";
  orderType: "MARKET" | "LIMIT";
  quantity: string;
  price?: string;
  leverage?: number;
  reduceOnly?: boolean;
  tradeSide?: "OPEN" | "CLOSE";
  positionId?: string;
  tpPrice?: string;
  slPrice?: string;
  tpStopType?: "MARK_PRICE" | "LAST_PRICE";
  slStopType?: "MARK_PRICE" | "LAST_PRICE";
}

export interface PlaceOrderResult {
  client_order_id: string;
  bitunix_order_id: string | null;
  status: string;
  dry_run: boolean;
  raw: unknown;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(
      `API ${response.status} ${response.statusText}: ${text || "no body"}`,
    );
  }
  return (await response.json()) as T;
}

export interface StrategyRun {
  id: number;
  strategy_name: string;
  status: "RUNNING" | "SUCCESS" | "NO_OP" | "FAILED" | null;
  triggered_by: string;
  details: Record<string, unknown> | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface StrategyInfo {
  name: string;
  enabled: boolean;
  last_run: StrategyRun | null;
}

export interface TopSignalEntriesConfig {
  count: number;
  scan_limit_max: number;
  scan_limit: number;
  kline_lookahead: number;
  kline_interval: string;
  kline_limit: number;
  cooldown_minutes: number;
  min_abs_change_pct: string;
  range_threshold: string;
  max_kline_concurrency: number;
  wf_gate_enabled: boolean;
  wf_lookback_minutes: number;
  wf_cooldown_minutes: number;
  wf_choppiness_max: string;
  margin_pct_of_balance: string;
  min_margin_usdt: string;
  tp_roi_pct: string;
  sl_roi_pct: string;
  min_tp_roi_pct: string;
  tpsl_stop_type: "MARK_PRICE" | "LAST_PRICE";
  hold_window_optimization_enabled: boolean;
  hold_window_min_minutes: number;
  hold_window_max_minutes: number;
  hold_window_step_minutes: number;
  hold_profit_threshold_pct: string;
}

export type TopSignalEntriesConfigPatch = Partial<TopSignalEntriesConfig>;

export interface TopSignalEntriesConfigResponse {
  config: TopSignalEntriesConfig;
  enabled: boolean;
  live_trading: boolean;
}

export interface CalibrationRun {
  id: number;
  status: "RUNNING" | "SUCCESS" | "FAILED" | null;
  triggered_by: string;
  lookback_minutes: number;
  top_n: number;
  summary: {
    global?: {
      tp_move_pct?: string | null;
      sl_move_pct?: string | null;
      symbol_count?: number;
    };
    per_symbol?: Record<
      string,
      {
        tp_move_pct: string;
        sl_move_pct: string;
        atr_pct: string;
        samples: number;
        last_close: string;
        abs_change_24h_pct: string;
      }
    >;
  } | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface AuditEventRow {
  id: number;
  level: "DEBUG" | "INFO" | "WARNING" | "ERROR" | null;
  event: string;
  message: string | null;
  payload: Record<string, unknown> | null;
  strategy_name: string | null;
  created_at: string | null;
}

export interface NormalizedPosition {
  symbol: string | null;
  side: "BUY" | "SELL" | null;
  qty: string | null;
  entry_price: string | null;
  mark_price: string | null;
  leverage: number | null;
  margin: string | null;
  realized_pnl: string | null;
  unrealized_pnl: string | null;
  roi_pct: string | null;
  liq_price: string | null;
  position_id: string | null;
  margin_mode: string | null;
  position_mode: string | null;
  opened_at: string | null;
  updated_at: string | null;
}

export interface NormalizedPositionsResponse {
  positions: NormalizedPosition[];
  totals: {
    count: number;
    unrealized_pnl_usdt: string;
    realized_pnl_usdt: string;
    margin_usdt: string;
  };
}

export interface DashboardSummary {
  generated_at: string;
  lookback_hours: number;
  lookback_days: number;
  orders: {
    total: number;
    last_24h: number;
    in_lookback_window?: number | null;
    by_status: Record<string, number>;
    top_symbols_30d: { symbol: string; count: number }[];
    by_strategy_30d: { strategy: string; count: number }[];
  };
  events: {
    total_24h: number;
    by_level_24h: Record<string, number>;
    recent: {
      id: number;
      created_at: string | null;
      level: string | null;
      event: string;
      message: string | null;
      strategy_name: string | null;
    }[];
    last_error_at: string | null;
  };
  strategy: {
    by_status_24h: Record<string, number>;
    last_success: { started_at: string | null; strategy_name: string } | null;
    last_failure: {
      started_at: string | null;
      strategy_name: string;
      error: string | null;
    } | null;
    last_calibration: {
      status: string | null;
      started_at: string | null;
      finished_at: string | null;
    } | null;
  };
  exchange: {
    sync_error: string | null;
    account: {
      margin_coin: string | null;
      available: string | null;
      margin: string | null;
      frozen: string | null;
      transfer: string | null;
      cross_unrealized_pnl: string | null;
      isolation_unrealized_pnl: string | null;
      bonus: string | null;
      position_mode: string | null;
    } | null;
    open_positions: {
      count: number;
      total_unrealized_pnl_usdt: string;
      total_margin_usdt: string;
      items: NormalizedPosition[];
    };
    closed_positions: {
      lookback_hours?: number;
      lookback_days: number;
      count: number;
      realized_pnl_usdt: string;
      win_rate_pct: string | null;
      wins: number;
      losses: number;
      avg_win_usdt: string | null;
      avg_loss_usdt: string | null;
      profit_factor?: string | null;
      expectancy_usdt?: string | null;
      max_drawdown_usdt?: string | null;
      top_winners: NormalizedPosition[];
      top_losers: NormalizedPosition[];
      per_symbol: { symbol: string; realized_pnl_usdt: string }[];
    };
  };
}

export interface SettingsSnapshot {
  generated_at: string;
  env: {
    app_env: string;
    strategy_runner_enabled: boolean;
    calibration_enabled: boolean;
    require_calibration_for_trading: boolean;
  };
  effective: {
    trading_paused: boolean;
    require_calibration_for_trading: boolean;
    strategy_runner_paused: boolean;
    strategy_runner_active: boolean;
    live_trading: boolean;
    strategies: Record<string, boolean>;
    new_position_open_allowed: boolean;
    new_position_block_reason: string | null;
  };
  runtime_overrides: Record<string, boolean>;
  strategy_config: {
    interval_seconds: number;
    calibration_interval_seconds: number;
    calibration_max_age_minutes: number;
    top_signal_entries: TopSignalEntriesConfig;
  };
  trading_blackout: TradingBlackoutSchedulePayload;
}

export type TradingBlackoutSchedulePayload = {
  timezone: string;
  days: Record<
    string,
    {
      mode: "open" | "block_all" | "block_ranges";
      block_ranges: { start: string; end: string }[];
    }
  >;
};

export interface PnlBreakdownTrade {
  symbol: string | null;
  side: string | null;
  realized_pnl_usdt: string;
  closed_at: string | null;
  roi_pct?: string | null;
}

export interface PnlSeriesBreakdown {
  per_symbol: { symbol: string; realized_pnl_usdt: string; count: number }[];
  by_side: Record<string, { count: number; wins: number; losses: number }>;
  top_winners: PnlBreakdownTrade[];
  top_losers: PnlBreakdownTrade[];
}

export interface TpSlCountRow {
  tp_count: number;
  sl_count: number;
}

export interface TpSlByHourBucket extends TpSlCountRow {
  hour: number;
}

export interface TpSlByWeekdayBucket extends TpSlCountRow {
  weekday: number;
  label: string;
}

export interface TpSlByWeekdayHourBucket extends TpSlByWeekdayBucket {
  by_hour: TpSlByHourBucket[];
}

export interface TpSlTimingStats {
  timezone: string;
  classification_note: string;
  by_hour: TpSlByHourBucket[];
  by_weekday: TpSlByWeekdayBucket[];
  by_weekday_hour: TpSlByWeekdayHourBucket[];
  total_tp: number;
  total_sl: number;
}

export interface TradeDurationSide {
  count: number;
  avg_duration_sec: number | null;
}

export interface TradeDurationBucket {
  wins: TradeDurationSide;
  losses: TradeDurationSide;
}

export interface TradeHoldDurationByWeekday extends TradeDurationBucket {
  weekday: number;
  label: string;
}

export interface TradeHoldDurationByHour extends TradeDurationBucket {
  hour: number;
}

export interface TradeHoldDurationStats {
  timezone: string;
  classification_note: string;
  skipped_no_duration: number;
  summary: TradeDurationBucket;
  by_weekday: TradeHoldDurationByWeekday[];
  by_hour: TradeHoldDurationByHour[];
}

export interface PnlSeriesResponse {
  lookback_hours: number;
  window_custom?: boolean;
  window_end_live?: boolean;
  bucket_hours: number;
  window_start?: string;
  window_end?: string;
  positions_in_window?: number;
  sync_error: string | null;
  buckets: { bucket_start: string; realized_pnl_usdt: string }[];
  cumulative: { at: string; cumulative_pnl_usdt: string }[];
  tp_sl_timing?: TpSlTimingStats;
  trade_hold_duration?: TradeHoldDurationStats;
  kpis: {
    count: number;
    realized_pnl_usdt: string;
    wins: number;
    losses: number;
    win_rate_pct: string | null;
    profit_factor: string | null;
    expectancy_usdt: string | null;
    max_drawdown_usdt: string;
    avg_win_usdt: string | null;
    avg_loss_usdt: string | null;
  };
  breakdown?: PnlSeriesBreakdown;
}

export interface AnalyticsOrdersWindow {
  lookback_hours: number;
  total: number;
  by_status: Record<string, number>;
  by_strategy: { strategy: string; count: number }[];
}

export interface AnalyticsStrategyWindow {
  lookback_hours: number;
  by_status: Record<string, number>;
}

export interface AnalyticsSummaryResponse {
  generated_at: string;
  lookback_hours: number;
  window_custom?: boolean;
  window_end_live?: boolean;
  window_start?: string;
  window_end?: string;
  bucket_hours: number;
  pnl: PnlSeriesResponse;
  orders: AnalyticsOrdersWindow;
  strategy: AnalyticsStrategyWindow;
}

export type AnalyticsSummaryQuery =
  | { lookbackHours: number; bucketHours?: number }
  | { windowStart: string; windowEnd?: string; bucketHours?: number };

export interface RuntimeSettingsPatch {
  trading_paused?: boolean;
  require_calibration_for_trading?: boolean;
  strategy_runner_paused?: boolean;
  bitunix_live_trading?: boolean;
  strategy_top_signal_entries_enabled?: boolean;
}

export interface MarketSymbolRow {
  symbol: string;
  max_leverage: number;
}

export interface CandleChartRow {
  time_ms: number;
  open: string;
  high: string;
  low: string;
  close: string;
}

export interface CleanLegRow {
  start_time_ms: number;
  end_time_ms: number;
  start_index: number;
  end_index: number;
  direction: "up" | "down";
  move_pct: string;
  choppiness: string;
  start_price: string;
  end_price: string;
}

export interface WalkForwardTradeRow {
  trade_index: number;
  entry_bar_index: number;
  exit_bar_index: number;
  chart_from_index: number;
  chart_to_index: number;
  entry_time_ms: number;
  exit_time_ms: number;
  predicted_side: "long" | "short";
  prediction_reason: string;
  first_touch: "tp" | "sl" | "none";
  entry_price: string;
  exit_price: string;
  tp_price: string;
  sl_price: string;
  median_move_pct_train: string;
  tp_move_pct: string;
  sl_move_pct: string;
  strategy_would_win: boolean;
  same_bar_ambiguous: boolean;
  direction_guess_correct: boolean;
}

export interface WalkForwardSequenceSummary {
  total_trades: number;
  tp_wins: number;
  sl_losses: number;
  no_result: number;
  direction_hits: number;
}

export interface WalkForwardCurrentSignal {
  enabled: boolean;
  disabled_reason: string | null;
  predicted_side: "long" | "short" | null;
  prediction_reason: string | null;
  entry_price: string | null;
  tp_price: string | null;
  sl_price: string | null;
  median_move_pct_train: string | null;
  tp_move_pct: string | null;
  sl_move_pct: string | null;
  train_bar_count: number;
}

export interface WalkForwardSequence {
  enabled: boolean;
  disabled_reason: string | null;
  cooldown_minutes: number;
  initial_split_fraction: string;
  first_checkpoint_time_ms: number | null;
  tp_median_multiplier: string;
  sl_median_multiplier: string;
  trades: WalkForwardTradeRow[];
  summary: WalkForwardSequenceSummary | null;
  current_signal: WalkForwardCurrentSignal;
}

export interface WalkForwardSequenceCore {
  enabled: boolean;
  disabled_reason: string | null;
  cooldown_minutes: number;
  initial_split_fraction: string;
  first_checkpoint_time_ms: number | null;
  tp_median_multiplier: string;
  sl_median_multiplier: string;
  trades: WalkForwardTradeRow[];
  summary: WalkForwardSequenceSummary | null;
}

export interface HoldWindowGridRow {
  hold_minutes: number;
  trades_evaluated: number;
  good_trades: number;
  good_rate_pct: string | null;
}

export interface HoldWindowBlock {
  enabled: boolean;
  profit_threshold_pct: string | null;
  grid_minutes: number[];
  hold_sim_interval?: string | null;
  hold_sim_kline_bar_minutes?: number | null;
  best_hold_minutes: number | null;
  best_good_rate_pct: string | null;
  rows: HoldWindowGridRow[];
}

export interface HoldWindowOptimizationInfo {
  enabled: boolean;
  min_minutes: number;
  max_minutes: number;
  step_minutes: number;
  profit_threshold_pct: string;
  hold_sim_interval?: string | null;
}

export interface TpslVariationRow {
  rank: number;
  tp_median_multiplier: string;
  sl_median_multiplier: string;
  label: string;
  resolved_tp_win_rate_pct: string | null;
  meets_target: boolean;
  resolved_count: number;
  trades_entered_last_48h_count: number;
  first_trade_tp_move_pct_raw: string | null;
  first_trade_sl_move_pct_raw: string | null;
  meets_min_tpsl_pct_profile: boolean;
  is_recommended: boolean;
  sequence: WalkForwardSequenceCore;
  hold_window?: HoldWindowBlock | null;
  best_hold_minutes?: number | null;
  hold_good_rate_pct?: string | null;
}

export interface WalkForwardTpslVariations {
  enabled: boolean;
  disabled_reason: string | null;
  target_tp_win_rate_pct: string;
  min_resolved_trades: number;
  any_variation_meets_target: boolean;
  has_recommended_variation: boolean;
  min_trades_last_48h_for_recommendation: number;
  lookback_hours: number;
  variation_tp_move_pct_min: string;
  variation_tp_move_pct_max: string;
  variation_sl_move_pct_min: string;
  variation_sl_move_pct_max: string;
  best_current_signal: WalkForwardCurrentSignal | null;
  variations: TpslVariationRow[];
}

export interface WalkForwardAggregate {
  total_runs: number;
  tp_first_count: number;
  sl_first_count: number;
  no_touch_count: number;
  direction_correct_count: number;
  strategy_win_rate_pct: string | null;
  direction_hit_rate_pct: string | null;
}

export interface WalkForwardBacktest {
  enabled: boolean;
  disabled_reason: string | null;
  time_split_fraction: string | null;
  train_start_time_ms: number | null;
  train_end_time_ms: number | null;
  checkpoint_time_ms: number | null;
  test_start_time_ms: number | null;
  test_end_time_ms: number | null;
  train_bar_count: number;
  test_bar_count: number;
  median_move_pct_train: string | null;
  tp_move_pct: string | null;
  sl_move_pct: string | null;
  entry_price: string | null;
  tp_price: string | null;
  sl_price: string | null;
  test_start_close: string | null;
  test_end_close: string | null;
  predicted_side: "long" | "short" | null;
  prediction_reason: string | null;
  test_net_move_pct: string | null;
  actual_test_side: "long" | "short" | null;
  direction_guess_correct: boolean | null;
  first_touch: "tp" | "sl" | "none" | null;
  first_touch_time_ms: number | null;
  same_bar_ambiguous: boolean | null;
  strategy_would_win: boolean | null;
  aggregate: WalkForwardAggregate | null;
}

export interface CoinAnalyzeResult {
  symbol: string;
  max_leverage: number;
  interval: string;
  kline_limit: number;
  lookback_minutes_requested: number;
  choppiness_max: string;
  candles: CandleChartRow[];
  clean_legs: CleanLegRow[];
  median_move_pct: string | null;
  mean_move_pct: string | null;
  clean_leg_count: number;
  all_leg_count: number;
  walk_forward: WalkForwardBacktest;
  walk_forward_sequence: WalkForwardSequence;
  walk_forward_tpsl_variations: WalkForwardTpslVariations;
  hold_window_optimization: HoldWindowOptimizationInfo;
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  ticker: (symbol: string) =>
    request<TickerInfo>(`/api/market/ticker/${encodeURIComponent(symbol)}`),
  marketSymbols: () => request<MarketSymbolRow[]>("/api/market/symbols"),
  coinAnalyze: (body: {
    symbol: string;
    lookback_minutes: number;
    walk_forward_cooldown_minutes?: number;
  }) =>
    request<CoinAnalyzeResult>("/api/market/coin-analyze", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  orders: (params?: {
    limit?: number;
    offset?: number;
    symbol?: string;
    lookbackHours?: number;
    lifecycle?: string;
  }) => {
    const usp = new URLSearchParams();
    if (params?.limit != null) usp.set("limit", String(params.limit));
    if (params?.offset != null) usp.set("offset", String(params.offset));
    if (params?.symbol) usp.set("symbol", params.symbol);
    if (params?.lookbackHours != null) {
      usp.set("lookback_hours", String(params.lookbackHours));
    }
    if (params?.lifecycle) usp.set("lifecycle", params.lifecycle);
    const qs = usp.toString();
    return request<OrderRow[]>(`/api/orders${qs ? `?${qs}` : ""}`);
  },
  ordersPnlTotals: (lookbackHours = 6, lifecycle?: string) => {
    const usp = new URLSearchParams();
    usp.set("lookback_hours", String(lookbackHours));
    if (lifecycle) usp.set("lifecycle", lifecycle);
    const qs = usp.toString();
    return request<OrdersPnlTotals>(`/api/orders/pnl-totals${qs ? `?${qs}` : ""}`);
  },
  placeOrder: (input: PlaceOrderInput) =>
    request<PlaceOrderResult>("/api/orders", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  positions: (symbol?: string) =>
    request<unknown>(
      `/api/positions${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ""}`,
    ),
  positionsNormalized: (symbol?: string) =>
    request<NormalizedPositionsResponse>(
      `/api/positions/normalized${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ""}`,
    ),
  dashboardSummary: (lookbackHours = 168) =>
    request<DashboardSummary>(
      `/api/dashboard/summary?lookback_hours=${lookbackHours}`,
    ),
  settingsSnapshot: () => request<SettingsSnapshot>("/api/settings"),
  patchSettings: (body: RuntimeSettingsPatch) =>
    request<{ applied: Record<string, boolean>; snapshot: SettingsSnapshot }>(
      "/api/settings",
      { method: "PATCH", body: JSON.stringify(body) },
    ),
  setTradingPause: (paused: boolean) =>
    request<{ trading_paused: boolean }>("/api/settings/trading-pause", {
      method: "POST",
      body: JSON.stringify({ paused }),
    }),
  putTradingBlackout: (schedule: TradingBlackoutSchedulePayload) =>
    request<{ schedule: TradingBlackoutSchedulePayload; snapshot: SettingsSnapshot }>(
      "/api/settings/trading-blackout",
      { method: "PUT", body: JSON.stringify(schedule) },
    ),
  analyticsSummary: (query: AnalyticsSummaryQuery = { lookbackHours: 24, bucketHours: 6 }) => {
    const bucketHours = query.bucketHours ?? 6;
    const usp = new URLSearchParams();
    usp.set("bucket_hours", String(bucketHours));
    if ("windowStart" in query && query.windowStart) {
      usp.set("window_start", query.windowStart);
      if (query.windowEnd) {
        usp.set("window_end", query.windowEnd);
      }
    } else {
      const hours = "lookbackHours" in query ? query.lookbackHours : 24;
      usp.set("lookback_hours", String(hours));
    }
    return request<AnalyticsSummaryResponse>(`/api/analytics/summary?${usp.toString()}`);
  },
  analyticsPnlSeries: (query: AnalyticsSummaryQuery = { lookbackHours: 24, bucketHours: 6 }) => {
    const bucketHours = query.bucketHours ?? 6;
    const usp = new URLSearchParams();
    usp.set("bucket_hours", String(bucketHours));
    if ("windowStart" in query && query.windowStart) {
      usp.set("window_start", query.windowStart);
      if (query.windowEnd) {
        usp.set("window_end", query.windowEnd);
      }
    } else {
      const hours = "lookbackHours" in query ? query.lookbackHours : 24;
      usp.set("lookback_hours", String(hours));
    }
    return request<PnlSeriesResponse>(`/api/analytics/pnl-series?${usp.toString()}`);
  },
  analyticsOrdersWindow: (lookbackHours = 24) =>
    request<AnalyticsOrdersWindow>(
      `/api/analytics/orders?lookback_hours=${lookbackHours}`,
    ),
  account: () => request<unknown>("/api/account"),
  strategies: () => request<StrategyInfo[]>("/api/strategies"),
  strategyRuns: (strategy?: string, limit = 50) =>
    request<StrategyRun[]>(
      `/api/strategies/runs?limit=${limit}${strategy ? `&strategy=${encodeURIComponent(strategy)}` : ""}`,
    ),
  triggerStrategy: (name: string) =>
    request<{ run_id: number; status: string }>(
      `/api/strategies/${encodeURIComponent(name)}/run`,
      { method: "POST" },
    ),
  getTopSignalEntriesConfig: () =>
    request<TopSignalEntriesConfigResponse>(
      "/api/strategies/top_signal_entries/config",
    ),
  putTopSignalEntriesConfig: (patch: TopSignalEntriesConfigPatch) =>
    request<{ config: TopSignalEntriesConfig }>(
      "/api/strategies/top_signal_entries/config",
      { method: "PUT", body: JSON.stringify(patch) },
    ),
  calibrationLatest: () =>
    request<{
      trading_enabled: boolean;
      trading_paused?: boolean;
      calibration_gate_open?: boolean;
      require_calibration_for_trading: boolean;
      max_age_minutes: number;
      now: string;
      next_run_after: string | null;
      latest: CalibrationRun | null;
      latest_successful: CalibrationRun | null;
    }>("/api/calibration/latest"),
  calibrationRuns: (limit = 20) =>
    request<CalibrationRun[]>(`/api/calibration/runs?limit=${limit}`),
  triggerCalibration: () =>
    request<{ queued: boolean }>(`/api/calibration/run`, { method: "POST" }),
  events: (params?: {
    level?: string;
    event_prefix?: string;
    strategy_name?: string;
    limit?: number;
  }) => {
    const usp = new URLSearchParams();
    if (params?.level) usp.set("level", params.level);
    if (params?.event_prefix) usp.set("event_prefix", params.event_prefix);
    if (params?.strategy_name) usp.set("strategy_name", params.strategy_name);
    usp.set("limit", String(params?.limit ?? 100));
    return request<AuditEventRow[]>(`/api/events?${usp.toString()}`);
  },
};
