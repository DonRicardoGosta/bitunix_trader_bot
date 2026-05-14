/**
 * Backend API kliens. Soha NEM beszél közvetlenül a Bitunix-szal;
 * mindent a saját FastAPI backendünkön keresztül routol.
 */

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://localhost:8000";

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
}

/** GET /api/orders/pnl-totals — összes saját DB rendelés PnL összesítője */
export interface OrdersPnlTotals {
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
  lookback_days: number;
  orders: {
    total: number;
    last_24h: number;
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
      lookback_days: number;
      count: number;
      realized_pnl_usdt: string;
      win_rate_pct: string | null;
      wins: number;
      losses: number;
      avg_win_usdt: string | null;
      avg_loss_usdt: string | null;
      top_winners: NormalizedPosition[];
      top_losers: NormalizedPosition[];
      per_symbol: { symbol: string; realized_pnl_usdt: string }[];
    };
  };
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

export interface TpslVariationRow {
  rank: number;
  tp_median_multiplier: string;
  sl_median_multiplier: string;
  label: string;
  resolved_tp_win_rate_pct: string | null;
  meets_target: boolean;
  resolved_count: number;
  sequence: WalkForwardSequenceCore;
}

export interface WalkForwardTpslVariations {
  enabled: boolean;
  disabled_reason: string | null;
  target_tp_win_rate_pct: string;
  min_resolved_trades: number;
  any_variation_meets_target: boolean;
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
  orders: (params?: { limit?: number; offset?: number; symbol?: string }) => {
    const usp = new URLSearchParams();
    if (params?.limit != null) usp.set("limit", String(params.limit));
    if (params?.offset != null) usp.set("offset", String(params.offset));
    if (params?.symbol) usp.set("symbol", params.symbol);
    const qs = usp.toString();
    return request<OrderRow[]>(`/api/orders${qs ? `?${qs}` : ""}`);
  },
  ordersPnlTotals: () => request<OrdersPnlTotals>("/api/orders/pnl-totals"),
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
  dashboardSummary: (lookbackDays = 7) =>
    request<DashboardSummary>(
      `/api/dashboard/summary?lookback_days=${lookbackDays}`,
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
  calibrationLatest: () =>
    request<{
      trading_enabled: boolean;
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
