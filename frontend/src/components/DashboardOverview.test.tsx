import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { DashboardOverview } from "./DashboardOverview";
import type { DashboardSummary } from "@/lib/api";

const originalFetch = globalThis.fetch;

function summary(overrides: Partial<DashboardSummary> = {}): DashboardSummary {
  return {
    generated_at: "2026-05-13T10:00:00Z",
    lookback_days: 7,
    orders: {
      total: 12,
      last_24h: 4,
      by_status: { NEW: 8, FILLED: 4 },
      top_symbols_30d: [{ symbol: "BTCUSDT", count: 8 }],
      by_strategy_30d: [{ strategy: "top_movers", count: 12 }],
    },
    events: {
      total_24h: 3,
      by_level_24h: { INFO: 2, ERROR: 1 },
      recent: [
        {
          id: 1,
          created_at: "2026-05-13T09:00:00Z",
          level: "INFO",
          event: "strategy.top_movers.signal",
          message: "ok",
          strategy_name: "top_movers",
        },
      ],
      last_error_at: null,
    },
    strategy: {
      by_status_24h: { SUCCESS: 2, FAILED: 0, NO_OP: 1 },
      last_success: {
        started_at: "2026-05-13T09:55:00Z",
        strategy_name: "top_movers",
      },
      last_failure: null,
      last_calibration: {
        status: "SUCCESS",
        started_at: "2026-05-13T08:00:00Z",
        finished_at: "2026-05-13T08:01:00Z",
      },
    },
    exchange: {
      sync_error: null,
      account: {
        margin_coin: "USDT",
        available: "100.00",
        margin: "20.00",
        frozen: "0",
        transfer: "100.00",
        cross_unrealized_pnl: "1.50",
        isolation_unrealized_pnl: "0",
        bonus: "0",
        position_mode: "HEDGE",
      },
      open_positions: {
        count: 2,
        total_unrealized_pnl_usdt: "1.50",
        total_margin_usdt: "20.00",
        items: [
          {
            symbol: "BTCUSDT",
            side: "BUY",
            qty: "0.01",
            entry_price: "60000",
            mark_price: "60500",
            leverage: 10,
            margin: "60",
            realized_pnl: "0",
            unrealized_pnl: "5",
            roi_pct: "8.33",
            liq_price: "55000",
            position_id: "p1",
            margin_mode: "CROSS",
            position_mode: "HEDGE",
            opened_at: "2026-05-13T09:00:00Z",
            updated_at: null,
          },
        ],
      },
      closed_positions: {
        lookback_days: 7,
        count: 3,
        realized_pnl_usdt: "25.50",
        win_rate_pct: "66.67",
        wins: 2,
        losses: 1,
        avg_win_usdt: "20.00",
        avg_loss_usdt: "-5.00",
        top_winners: [
          {
            symbol: "BTCUSDT",
            side: "BUY",
            qty: null,
            entry_price: "60000",
            mark_price: null,
            leverage: 10,
            margin: null,
            realized_pnl: "25",
            unrealized_pnl: "0",
            roi_pct: "8.33",
            liq_price: null,
            position_id: "win-1",
            margin_mode: null,
            position_mode: null,
            opened_at: null,
            updated_at: null,
          },
        ],
        top_losers: [],
        per_symbol: [{ symbol: "BTCUSDT", realized_pnl_usdt: "25.50" }],
      },
    },
    ...overrides,
  };
}

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("<DashboardOverview />", () => {
  it("renders KPI cards with account equity and PnL", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify(summary()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ) as unknown as typeof fetch;

    render(<DashboardOverview />);
    await waitFor(() =>
      expect(screen.getByText("Számlaegyenleg (equity)")).toBeInTheDocument(),
    );
    // Equity = available + margin + cross_upnl = 100 + 20 + 1.5 = 121.5
    expect(screen.getByText("121.5000")).toBeInTheDocument();
    expect(screen.getByText("Foglalt margin")).toBeInTheDocument();
    expect(screen.getAllByText("Nyitott PnL").length).toBeGreaterThan(0);
    // Win rate 66.67% jelenjen meg (több helyen is — KPI hint + statisztika)
    expect(screen.getAllByText(/66\.67%/).length).toBeGreaterThan(0);
    // Top winners
    expect(screen.getByText("Top winners (zárt)")).toBeInTheDocument();
  });

  it("shows sync_error banner when set", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(
        JSON.stringify(
          summary({
            exchange: {
              ...summary().exchange,
              sync_error: "API kulcs hiányzik",
            } as DashboardSummary["exchange"],
          }),
        ),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    ) as unknown as typeof fetch;

    render(<DashboardOverview />);
    await waitFor(() =>
      expect(screen.getByText(/API kulcs hiányzik/)).toBeInTheDocument(),
    );
  });
});
