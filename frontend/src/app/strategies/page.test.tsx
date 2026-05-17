import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StrategiesPage from "./page";
import { WithRefreshProvider } from "@/contexts/RefreshIntervalContext";

const originalFetch = globalThis.fetch;

function jsonResponse(data: unknown) {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

interface CallEntry {
  url: string;
  method: string;
}

let calls: CallEntry[] = [];

beforeEach(() => {
  calls = [];
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = (init?.method ?? "GET").toUpperCase();
    calls.push({ url, method });

    if (url.endsWith("/api/strategies/top_signal_entries/config")) {
      return jsonResponse({
        config: {
          count: 10,
          scan_limit_max: 1000,
          scan_limit: 1000,
          kline_lookahead: 1000,
          kline_interval: "15m",
          kline_limit: 80,
          cooldown_minutes: 240,
          min_abs_change_pct: "1.0",
          range_threshold: "0.60",
          max_kline_concurrency: 10,
          wf_gate_enabled: true,
          wf_lookback_minutes: 4320,
          wf_cooldown_minutes: 60,
          wf_choppiness_max: "1.72",
          margin_pct_of_balance: "0.01",
          min_margin_usdt: "0.2",
          tp_roi_pct: "200",
          sl_roi_pct: "100",
          min_tp_roi_pct: "60",
          tpsl_stop_type: "MARK_PRICE",
        },
        enabled: true,
        live_trading: true,
      });
    }
    if (url.endsWith("/api/settings")) {
      return jsonResponse({
        generated_at: "2026-05-13T10:00:00Z",
        env: {
          app_env: "development",
          strategy_runner_enabled: true,
          calibration_enabled: true,
          require_calibration_for_trading: true,
        },
        effective: {
          trading_paused: false,
          require_calibration_for_trading: true,
          strategy_runner_paused: false,
          strategy_runner_active: true,
          live_trading: true,
          strategies: { top_signal_entries: true },
          new_position_open_allowed: true,
          new_position_block_reason: null,
        },
        runtime_overrides: {},
        strategy_config: {
          interval_seconds: 30,
          calibration_interval_seconds: 3600,
          calibration_max_age_minutes: 180,
          top_signal_entries: {
            count: 10,
            scan_limit_max: 1000,
            scan_limit: 1000,
            kline_lookahead: 1000,
            kline_interval: "15m",
            kline_limit: 80,
            cooldown_minutes: 240,
            min_abs_change_pct: "1.0",
            range_threshold: "0.60",
            max_kline_concurrency: 10,
            wf_gate_enabled: true,
            wf_lookback_minutes: 4320,
            wf_cooldown_minutes: 60,
            wf_choppiness_max: "1.72",
            margin_pct_of_balance: "0.01",
            min_margin_usdt: "0.2",
            tp_roi_pct: "200",
            sl_roi_pct: "100",
            min_tp_roi_pct: "60",
            tpsl_stop_type: "MARK_PRICE",
          },
        },
        trading_blackout: { timezone: "UTC", days: {} },
      });
    }
    if (url.endsWith("/api/strategies")) {
      return jsonResponse([
        {
          name: "top_signal_entries",
          enabled: true,
          last_run: {
            id: 1,
            strategy_name: "top_signal_entries",
            status: "SUCCESS",
            triggered_by: "manual",
            details: {
              placed_orders: [{ symbol: "BTCUSDT" }, { symbol: "ETHUSDT" }],
              skipped: [],
              margin_per_position_usdt: "1.00",
            },
            error: null,
            started_at: "2026-05-13T10:00:00Z",
            finished_at: "2026-05-13T10:00:02Z",
          },
        },
      ]);
    }
    if (url.includes("/api/strategies/runs?")) {
      return jsonResponse([
        {
          id: 1,
          strategy_name: "top_signal_entries",
          status: "SUCCESS",
          triggered_by: "manual",
          details: {
            placed_orders: [{ symbol: "BTCUSDT" }, { symbol: "ETHUSDT" }],
            skipped: [],
            margin_per_position_usdt: "1.00",
          },
          error: null,
          started_at: "2026-05-13T10:00:00Z",
          finished_at: "2026-05-13T10:00:02Z",
        },
      ]);
    }
    if (url.endsWith("/api/strategies/top_signal_entries/run")) {
      return jsonResponse({ run_id: 42, status: "SUCCESS" });
    }
    return jsonResponse({});
  }) as unknown as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("<StrategiesPage />", () => {
  it("renders strategy with SUCCESS badge and placed counts", async () => {
    const { container } = render(
      <WithRefreshProvider>
        <StrategiesPage />
      </WithRefreshProvider>,
    );
    await waitFor(() =>
      expect(screen.getAllByText("top_signal_entries").length).toBeGreaterThan(0),
    );
    expect(screen.getAllByText("SUCCESS").length).toBeGreaterThan(0);
    expect(container.textContent).toContain("placed 2");
    expect(container.textContent).toContain("skip 0");
  });

  it("triggers strategy on button click", async () => {
    render(
      <WithRefreshProvider>
        <StrategiesPage />
      </WithRefreshProvider>,
    );
    const btn = await screen.findByRole("button", { name: /Indítás most/i });
    await userEvent.click(btn);
    await waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.method === "POST"
              && c.url.endsWith("/api/strategies/top_signal_entries/run"),
        ),
      ).toBe(true),
    );
  });
});
