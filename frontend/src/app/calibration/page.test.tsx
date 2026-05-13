import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CalibrationPage from "./page";

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
            global: { tp_move_pct: "1.50", sl_move_pct: "0.75", symbol_count: 2 },
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
  it("shows trading enabled banner and global TP/SL", async () => {
    render(<CalibrationPage />);
    await waitFor(() =>
      expect(screen.getByText(/Trading/i)).toBeInTheDocument(),
    );
    expect(screen.getByText("engedélyezve")).toBeInTheDocument();
    // R:R = 1.5 / 0.75 = 2.00
    expect(screen.getByText("2.00:1")).toBeInTheDocument();
    expect(screen.getByText("BTCUSDT")).toBeInTheDocument();
  });

  it("triggers calibration on button click", async () => {
    render(<CalibrationPage />);
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
