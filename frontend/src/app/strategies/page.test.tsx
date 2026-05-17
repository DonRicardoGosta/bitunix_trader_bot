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
    if (url.includes("/api/strategies/runs")) {
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
    expect(container.textContent).toContain("placed: 2");
    expect(container.textContent).toContain("skipped: 0");
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
