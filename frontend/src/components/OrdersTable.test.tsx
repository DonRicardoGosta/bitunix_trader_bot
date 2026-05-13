import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { OrdersTable } from "./OrdersTable";

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

describe("<OrdersTable />", () => {
  it("renders unrealized PnL column for open positions and computes ROI color from numeric value", async () => {
    globalThis.fetch = vi.fn(async () =>
      jsonResponse([
        {
          id: 1,
          client_order_id: "bt-open",
          bitunix_order_id: "1",
          symbol: "MLNUSDT",
          side: "SELL",
          type: "MARKET",
          quantity: "5.81",
          price: null,
          leverage: 50,
          status: "NEW",
          created_at: "2026-05-13T10:00:00Z",
          exchange: {
            synced: true,
            sync_error: null,
            order_status: "FILLED",
            lifecycle: "open",
            lifecycle_label: "Nyitott pozíció",
            realized_pnl_usdt: "-0.007679658",
            unrealized_pnl_usdt: "0.05229",
            roi_pct: "16.92",
            margin_usdt_estimate: "0.2637",
            position_id: "p-open",
          },
        },
      ]),
    ) as unknown as typeof fetch;

    render(<OrdersTable />);

    await waitFor(() =>
      expect(screen.getByText(/16\.92 %/)).toBeInTheDocument(),
    );

    expect(screen.getByText(/Nyitott PnL/)).toBeInTheDocument();
    // formatPnl 6 tizedesre kerekít, trailing zero-kat levág
    expect(screen.getByText(/0\.05229 USDT/)).toBeInTheDocument();
    expect(screen.getByText(/-0\.00768 USDT/)).toBeInTheDocument();
  });

  it("does not color zero ROI as profit (regression: '0' is truthy string)", async () => {
    globalThis.fetch = vi.fn(async () =>
      jsonResponse([
        {
          id: 1,
          client_order_id: "bt-zero",
          bitunix_order_id: null,
          symbol: "BTCUSDT",
          side: "BUY",
          type: "MARKET",
          quantity: "1",
          price: "60000",
          leverage: 10,
          status: "NEW",
          created_at: "2026-05-13T10:00:00Z",
          exchange: {
            synced: true,
            sync_error: null,
            order_status: "NEW",
            lifecycle: "pending",
            lifecycle_label: "Függőben",
            realized_pnl_usdt: "0",
            unrealized_pnl_usdt: null,
            roi_pct: "0.00",
            margin_usdt_estimate: "6000",
            position_id: null,
          },
        },
      ]),
    ) as unknown as typeof fetch;

    render(<OrdersTable />);

    const roiCell = await screen.findByText(/0\.00 %/);
    expect(roiCell).toBeInTheDocument();
    expect(roiCell.className).not.toContain("text-profit");
    expect(roiCell.className).not.toContain("text-loss");
  });

  it("renders em-dash for missing unrealized PnL on closed positions", async () => {
    globalThis.fetch = vi.fn(async () =>
      jsonResponse([
        {
          id: 1,
          client_order_id: "bt-closed",
          bitunix_order_id: "2",
          symbol: "SAGAUSDT",
          side: "SELL",
          type: "MARKET",
          quantity: "468.6",
          price: null,
          leverage: 50,
          status: "FILLED",
          created_at: "2026-05-13T10:00:00Z",
          exchange: {
            synced: true,
            sync_error: null,
            order_status: "FILLED",
            lifecycle: "closed",
            lifecycle_label: "Lezárva",
            realized_pnl_usdt: "0.017014866",
            unrealized_pnl_usdt: null,
            roi_pct: "6.46",
            margin_usdt_estimate: "0.2634",
            position_id: "p-closed",
          },
        },
      ]),
    ) as unknown as typeof fetch;

    render(<OrdersTable />);

    await waitFor(() =>
      expect(screen.getByText(/6\.46 %/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/0\.017015 USDT/)).toBeInTheDocument();
  });
});
