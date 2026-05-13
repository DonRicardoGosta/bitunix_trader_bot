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

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  ticker: (symbol: string) =>
    request<TickerInfo>(`/api/market/ticker/${encodeURIComponent(symbol)}`),
  orders: () => request<OrderRow[]>("/api/orders"),
  placeOrder: (input: PlaceOrderInput) =>
    request<PlaceOrderResult>("/api/orders", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  positions: (symbol?: string) =>
    request<unknown>(
      `/api/positions${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ""}`,
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
