import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OrdersTable } from "./OrdersTable";
import { WithRefreshProvider } from "@/contexts/RefreshIntervalContext";

const originalFetch = globalThis.fetch;

function jsonResponse(data: unknown) {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function order(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    client_order_id: "bt-x",
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
      lifecycle: "open",
      lifecycle_label: "Nyitott pozíció",
      realized_pnl_usdt: "0",
      unrealized_pnl_usdt: null,
      roi_pct: "0.00",
      margin_usdt_estimate: "6000",
      position_id: null,
    },
    ...overrides,
  };
}

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("<OrdersTable /> (grouped)", () => {
  it("groups orders by symbol and shows aggregated badges", async () => {
    globalThis.fetch = vi.fn(async () =>
      jsonResponse([
        order({
          id: 1,
          client_order_id: "bt-btc-1",
          symbol: "BTCUSDT",
          exchange: {
            ...order().exchange,
            lifecycle: "open",
            unrealized_pnl_usdt: "100",
            realized_pnl_usdt: "0",
          },
        }),
        order({
          id: 2,
          client_order_id: "bt-btc-2",
          symbol: "BTCUSDT",
          side: "SELL",
          exchange: {
            ...order().exchange,
            lifecycle: "closed",
            lifecycle_label: "Lezárva",
            realized_pnl_usdt: "50",
            unrealized_pnl_usdt: null,
          },
        }),
        order({
          id: 3,
          client_order_id: "bt-eth-1",
          symbol: "ETHUSDT",
          exchange: {
            ...order().exchange,
            lifecycle: "open",
            unrealized_pnl_usdt: "-25",
            realized_pnl_usdt: "0",
          },
        }),
      ]),
    ) as unknown as typeof fetch;

    render(
      <WithRefreshProvider>
        <OrdersTable />
      </WithRefreshProvider>,
    );
    // Várjuk meg a load-ot
    await waitFor(() =>
      expect(screen.getByText("BTCUSDT")).toBeInTheDocument(),
    );
    expect(screen.getByText("ETHUSDT")).toBeInTheDocument();
    // Csoport-szintű badge-ek (per-symbol rendelés-szám az inner összesítőben)
    const btcRow = screen.getByRole("button", { name: /BTCUSDT/ });
    expect(btcRow.textContent).toMatch(/2 rendelés/);
    const ethRow = screen.getByRole("button", { name: /ETHUSDT/ });
    expect(ethRow.textContent).toMatch(/1 rendelés/);
  });

  it("expands a group on click and shows inner table rows", async () => {
    globalThis.fetch = vi.fn(async () =>
      jsonResponse([
        order({
          id: 7,
          symbol: "SAGAUSDT",
          exchange: {
            ...order().exchange,
            lifecycle: "closed",
            lifecycle_label: "Lezárva",
            realized_pnl_usdt: "0.017",
            unrealized_pnl_usdt: null,
            roi_pct: "6.46",
          },
        }),
      ]),
    ) as unknown as typeof fetch;

    render(
      <WithRefreshProvider>
        <OrdersTable />
      </WithRefreshProvider>,
    );
    const header = await screen.findByRole("button", { name: /SAGAUSDT/ });
    expect(header).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(header);
    expect(header).toHaveAttribute("aria-expanded", "true");
    await waitFor(() => expect(screen.getByText(/6\.46 %/)).toBeInTheDocument());
    // Az inner tábla státusz oszlopa megjelenik
    expect(screen.getAllByText("Lezárva").length).toBeGreaterThan(0);
  });

  it("filters by symbol search input", async () => {
    globalThis.fetch = vi.fn(async () =>
      jsonResponse([
        order({ id: 1, symbol: "BTCUSDT" }),
        order({ id: 2, symbol: "ETHUSDT" }),
      ]),
    ) as unknown as typeof fetch;

    render(
      <WithRefreshProvider>
        <OrdersTable />
      </WithRefreshProvider>,
    );
    await screen.findByText("BTCUSDT");
    expect(screen.getByText("ETHUSDT")).toBeInTheDocument();

    const search = screen.getByLabelText(/Szimbólum szűrő/);
    await userEvent.type(search, "BTC");
    await waitFor(() =>
      expect(screen.queryByText("ETHUSDT")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("BTCUSDT")).toBeInTheDocument();
  });

  it("does not color zero ROI as profit (regression: '0' string truthy)", async () => {
    globalThis.fetch = vi.fn(async () =>
      jsonResponse([
        order({
          id: 1,
          symbol: "FOOUSDT",
          exchange: {
            ...order().exchange,
            roi_pct: "0.00",
            realized_pnl_usdt: "0",
          },
        }),
      ]),
    ) as unknown as typeof fetch;

    render(
      <WithRefreshProvider>
        <OrdersTable />
      </WithRefreshProvider>,
    );
    const header = await screen.findByRole("button", { name: /FOOUSDT/ });
    await userEvent.click(header);
    const roiCell = await screen.findByText(/^0\.00 %$/);
    expect(roiCell.className).not.toContain("text-profit");
    expect(roiCell.className).not.toContain("text-loss");
  });
});
