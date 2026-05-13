import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { TradingGateBanner } from "./TradingGateBanner";

const originalFetch = globalThis.fetch;

function jsonResponse(data: unknown) {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("<TradingGateBanner />", () => {
  it("shows blocking banner when trading_enabled=false", async () => {
    beforeEach;
    globalThis.fetch = vi.fn(async () =>
      jsonResponse({
        trading_enabled: false,
        require_calibration_for_trading: true,
        max_age_minutes: 180,
        now: "x",
        next_run_after: null,
        latest: null,
        latest_successful: null,
      }),
    ) as unknown as typeof fetch;

    render(<TradingGateBanner />);
    await waitFor(() =>
      expect(screen.getByText(/Trading le van tiltva/)).toBeInTheDocument(),
    );
  });

  it("shows green confirmation when trading_enabled=true", async () => {
    globalThis.fetch = vi.fn(async () =>
      jsonResponse({
        trading_enabled: true,
        require_calibration_for_trading: true,
        max_age_minutes: 180,
        now: "x",
        next_run_after: null,
        latest: { status: "SUCCESS" },
        latest_successful: {
          finished_at: "2026-05-13T09:00:00Z",
        },
      }),
    ) as unknown as typeof fetch;

    render(<TradingGateBanner />);
    await waitFor(() =>
      expect(screen.getByText(/Trading engedélyezve/)).toBeInTheDocument(),
    );
  });
});
