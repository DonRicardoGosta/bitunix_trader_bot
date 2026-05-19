import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import SettingsPage from "./page";
import { WithRefreshProvider } from "@/contexts/RefreshIntervalContext";

const originalFetch = globalThis.fetch;

describe("SettingsPage", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("renders control center title", async () => {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/settings") && !url.includes("trading-pause")) {
        return new Response(
          JSON.stringify({
            generated_at: "2026-01-01T00:00:00Z",
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
              live_trading: false,
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
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response("{}", { status: 404 });
    }) as typeof fetch;

    render(
      <WithRefreshProvider>
        <SettingsPage />
      </WithRefreshProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("Vezérlőpult")).toBeInTheDocument();
    });
  });
});
