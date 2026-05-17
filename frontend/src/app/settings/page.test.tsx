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
              bitunix_live_trading: false,
              strategy_runner_enabled: true,
              calibration_enabled: true,
              require_calibration_for_trading: true,
              strategy_top_signal_entries_enabled: true,
            },
            effective: {
              trading_paused: false,
              require_calibration_for_trading: true,
              strategy_runner_paused: false,
              strategy_runner_active: true,
              live_trading: true,
              strategies: { top_signal_entries: true },
            },
            runtime_overrides: {},
            strategy_config: { interval_seconds: 30 },
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
