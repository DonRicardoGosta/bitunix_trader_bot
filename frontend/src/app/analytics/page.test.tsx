import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import AnalyticsPage from "./page";
import type { AnalyticsSummaryResponse } from "@/lib/api";
import { WithRefreshProvider } from "@/contexts/RefreshIntervalContext";

const originalFetch = globalThis.fetch;

function summary(lookbackHours = 6): AnalyticsSummaryResponse {
  return {
    generated_at: "2026-05-16T10:00:00Z",
    lookback_hours: lookbackHours,
    bucket_hours: 1,
    pnl: {
      lookback_hours: lookbackHours,
      bucket_hours: 1,
      window_start: "2026-05-16T04:00:00Z",
      window_end: "2026-05-16T10:00:00Z",
      positions_in_window: 2,
      sync_error: null,
      buckets: [
        { bucket_start: "2026-05-16T04:00:00Z", realized_pnl_usdt: "1.5" },
        { bucket_start: "2026-05-16T05:00:00Z", realized_pnl_usdt: "0" },
      ],
      cumulative: [
        { at: "2026-05-16T04:00:00Z", cumulative_pnl_usdt: "0" },
        { at: "2026-05-16T10:00:00Z", cumulative_pnl_usdt: "1.5" },
      ],
      kpis: {
        count: 2,
        realized_pnl_usdt: "1.5",
        wins: 1,
        losses: 1,
        win_rate_pct: "50.00",
        profit_factor: "1.5",
        expectancy_usdt: "0.75",
        max_drawdown_usdt: "0.5",
        avg_win_usdt: "1.5",
        avg_loss_usdt: "-0.5",
      },
      breakdown: {
        per_symbol: [{ symbol: "BTCUSDT", realized_pnl_usdt: "1.5", count: 2 }],
        by_side: { LONG: { count: 2, wins: 1, losses: 1 } },
        top_winners: [],
        top_losers: [],
      },
    },
    orders: {
      lookback_hours: lookbackHours,
      total: 3,
      by_status: { NEW: 2, FILLED: 1 },
      by_strategy: [{ strategy: "top_movers", count: 3 }],
    },
    strategy: {
      lookback_hours: lookbackHours,
      by_status: { SUCCESS: 1 },
    },
  };
}

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("AnalyticsPage", () => {
  it("renders summary KPIs and DB panels", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => summary(6),
    });

    render(
      <WithRefreshProvider>
        <AnalyticsPage />
      </WithRefreshProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("Analytics")).toBeInTheDocument();
    });
    expect(screen.getByText("Realized PnL")).toBeInTheDocument();
    expect(screen.getByText("Rendelések (DB)")).toBeInTheDocument();
    expect(screen.getByText("PnL szimbólumonként")).toBeInTheDocument();
  });
});
