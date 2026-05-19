import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CalibrationPage from "./page";
import { WithRefreshProvider } from "@/contexts/RefreshIntervalContext";

const originalFetch = globalThis.fetch;

function jsonResponse(data: unknown) {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

const calls: { url: string; method: string }[] = [];

beforeEach(() => {
  calls.length = 0;
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = (init?.method ?? "GET").toUpperCase();
    calls.push({ url, method });

    if (url.endsWith("/api/calibration/latest")) {
      return jsonResponse({
        trading_enabled: true,
        require_calibration_for_trading: true,
        max_age_minutes: 180,
        now: "2026-05-13T10:00:00Z",
        next_run_after: "2026-05-13T11:00:00Z",
        latest: {
          id: 1,
          status: "SUCCESS",
          triggered_by: "scheduler",
          lookback_minutes: 120,
          top_n: 20,
          summary: {
            global: {
              tp_move_pct: "1.50",
              sl_move_pct: "0.75",
              symbol_count: 2,
            },
            per_symbol: {
              BTCUSDT: {
                tp_move_pct: "1.20",
                sl_move_pct: "0.60",
                atr_pct: "0.40",
                samples: 120,
                last_close: "50000",
                abs_change_24h_pct: "2.5",
              },
            },
          },
          error: null,
          started_at: "2026-05-13T09:00:00Z",
          finished_at: "2026-05-13T09:00:30Z",
        },
        latest_successful: {
          id: 1,
          status: "SUCCESS",
          triggered_by: "scheduler",
          lookback_minutes: 120,
          top_n: 20,
          summary: {
            mode: "candidate_backtest",
            candidates_target: 2,
            candidates_found: 1,
            scanned_symbols: 5,
            qualified_candidates: [
              {
                symbol: "BTCUSDT",
                rank: 1,
                abs_change_24h_pct: "2.5",
                tp_roi_pct: "100",
                sl_roi_pct: "50",
                backtest_win_rate_pct: "85.00",
                variation_label: "TP100/SL50",
                trade_count: 6,
                variations: [
                  {
                    label: "TP100/SL50",
                    tp_roi_pct: "100",
                    sl_roi_pct: "50",
                    resolved_tp_win_rate_pct: "85.00",
                    meets_target: true,
                    summary: { total_trades: 6, tp_wins: 5, sl_losses: 1, no_result: 0 },
                  },
                ],
              },
            ],
            per_symbol: {
              BTCUSDT: {
                tp_move_pct: "5.0",
                sl_move_pct: "2.5",
                tp_roi_pct: "100",
                sl_roi_pct: "50",
                backtest_win_rate_pct: "85.00",
                variation_label: "TP100/SL50",
                atr_pct: "0",
                samples: 672,
                last_close: "50000",
                abs_change_24h_pct: "2.5",
              },
            },
          },
          error: null,
          started_at: "2026-05-13T09:00:00Z",
          finished_at: "2026-05-13T09:00:30Z",
        },
      });
    }
    if (url.includes("/api/calibration/runs/") && url.includes("/symbols")) {
      return jsonResponse({
        calibration_id: 1,
        total: 2,
        limit: 100,
        offset: 0,
        items: [
          {
            id: 10,
            calibration_id: 1,
            symbol: "ETHUSDT",
            scan_rank: 2,
            abs_change_24h_pct: "3.0",
            reason: "no_variation_meets_target",
            is_qualified: false,
            max_win_rate_pct: "72.00",
            best_win_rate_pct: null,
            best_variation_label: null,
            best_total_trades: 20,
            fetch_error: null,
            variations: null,
            created_at: "2026-05-13T09:00:30Z",
          },
          {
            id: 11,
            calibration_id: 1,
            symbol: "BTCUSDT",
            scan_rank: 1,
            abs_change_24h_pct: "2.5",
            reason: "qualified",
            is_qualified: true,
            max_win_rate_pct: "85.00",
            best_win_rate_pct: "85.00",
            best_variation_label: "TP100/SL50",
            best_total_trades: 6,
            fetch_error: null,
            variations: null,
            created_at: "2026-05-13T09:00:30Z",
          },
        ],
      });
    }
    if (url.includes("/api/calibration/runs")) {
      return jsonResponse([]);
    }
    if (url.endsWith("/api/calibration/run")) {
      return jsonResponse({ queued: true });
    }
    return jsonResponse({});
  }) as unknown as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("<CalibrationPage />", () => {
  it("shows trading enabled and qualified backtest candidates", async () => {
    render(
      <WithRefreshProvider>
        <CalibrationPage />
      </WithRefreshProvider>,
    );
    await waitFor(() =>
      expect(screen.getByText(/Tradelés/i)).toBeInTheDocument(),
    );
    expect(screen.getByText("engedélyezve")).toBeInTheDocument();
    expect(screen.getAllByText("BTCUSDT").length).toBeGreaterThan(0);
    expect(screen.getAllByText("85.00%").length).toBeGreaterThan(0);
    expect(screen.getByText(/Összes coin backtest/i)).toBeInTheDocument();
    expect(screen.getByText(/Minősített jelöltek/i)).toBeInTheDocument();
  });

  it("triggers calibration on button click", async () => {
    render(
      <WithRefreshProvider>
        <CalibrationPage />
      </WithRefreshProvider>,
    );
    await screen.findByText("engedélyezve");
    await userEvent.click(
      screen.getByRole("button", { name: /Kalibrálás most/i }),
    );
    await waitFor(() =>
      expect(
        calls.some(
          (c) => c.method === "POST" && c.url.endsWith("/api/calibration/run"),
        ),
      ).toBe(true),
    );
  });
});
