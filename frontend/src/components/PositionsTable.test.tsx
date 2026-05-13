import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PositionsTable } from "./PositionsTable";
import { WithRefreshProvider } from "@/contexts/RefreshIntervalContext";

const originalFetch = globalThis.fetch;

const PAYLOAD = {
  positions: [
    {
      symbol: "BTCUSDT",
      side: "BUY",
      qty: "0.1",
      entry_price: "60000",
      mark_price: "61000",
      leverage: 20,
      margin: "300",
      realized_pnl: "-0.5",
      unrealized_pnl: "100",
      roi_pct: "33.17",
      liq_price: "55000",
      position_id: "p1",
      margin_mode: "CROSS",
      position_mode: "HEDGE",
      opened_at: "2026-05-13T09:00:00Z",
      updated_at: null,
    },
    {
      symbol: "ETHUSDT",
      side: "SELL",
      qty: "1",
      entry_price: "3000",
      mark_price: "2990",
      leverage: 5,
      margin: "600",
      realized_pnl: "0",
      unrealized_pnl: "10",
      roi_pct: "1.67",
      liq_price: "3300",
      position_id: "p2",
      margin_mode: "CROSS",
      position_mode: "HEDGE",
      opened_at: "2026-05-13T09:30:00Z",
      updated_at: null,
    },
  ],
  totals: {
    count: 2,
    unrealized_pnl_usdt: "110",
    realized_pnl_usdt: "-0.5",
    margin_usdt: "900",
  },
};

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("<PositionsTable />", () => {
  it("renders KPIs and a row per position", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify(PAYLOAD), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ) as unknown as typeof fetch;

    render(
      <WithRefreshProvider>
        <PositionsTable />
      </WithRefreshProvider>,
    );
    await waitFor(() =>
      expect(screen.getByText("BTCUSDT")).toBeInTheDocument(),
    );
    expect(screen.getByText("ETHUSDT")).toBeInTheDocument();
    // KPI-k és táblafejléc is "Nyitott PnL"-t használ → getAllByText
    expect(screen.getByText("Foglalt margin")).toBeInTheDocument();
    expect(screen.getAllByText("Nyitott PnL").length).toBeGreaterThan(0);
  });

  it("filters by symbol search", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify(PAYLOAD), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ) as unknown as typeof fetch;

    render(
      <WithRefreshProvider>
        <PositionsTable />
      </WithRefreshProvider>,
    );
    await screen.findByText("BTCUSDT");
    const search = screen.getByLabelText(/Szimbólum/);
    await userEvent.type(search, "ETH");
    await waitFor(() =>
      expect(screen.queryByText("BTCUSDT")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("ETHUSDT")).toBeInTheDocument();
  });
});
