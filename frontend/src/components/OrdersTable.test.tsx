import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WithLiveUpdatesProvider } from "@/contexts/LiveUpdatesContext";
import { OrdersTable } from "./OrdersTable";

function renderOrdersTable(props?: { lookbackHours?: number; refreshIntervalMs?: number }) {
  return render(
    <WithLiveUpdatesProvider>
      <OrdersTable refreshIntervalMs={60_000} {...props} />
    </WithLiveUpdatesProvider>,
  );
}

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
            lifecycle: "closed",
            lifecycle_label: "Lezárva",
            realized_pnl_usdt: "10",
            unrealized_pnl_usdt: null,
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
            lifecycle: "closed",
            lifecycle_label: "Lezárva",
            realized_pnl_usdt: "-25",
            unrealized_pnl_usdt: null,
          },
        }),
      ]),
    ) as unknown as typeof fetch;

    renderOrdersTable();
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

    renderOrdersTable();
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
        order({
          id: 1,
          symbol: "BTCUSDT",
          exchange: { ...order().exchange, lifecycle: "closed", lifecycle_label: "Lezárva" },
        }),
        order({
          id: 2,
          symbol: "ETHUSDT",
          exchange: { ...order().exchange, lifecycle: "closed", lifecycle_label: "Lezárva" },
        }),
      ]),
    ) as unknown as typeof fetch;

    renderOrdersTable();
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
            lifecycle: "closed",
            lifecycle_label: "Lezárva",
            roi_pct: "0.00",
            realized_pnl_usdt: "0",
          },
        }),
      ]),
    ) as unknown as typeof fetch;

    renderOrdersTable();
    const header = await screen.findByRole("button", { name: /FOOUSDT/ });
    await userEvent.click(header);
    const roiCell = await screen.findByText(/^0\.00 %$/);
    expect(roiCell.className).not.toContain("text-profit");
    expect(roiCell.className).not.toContain("text-loss");
  });

  it("shows entry summary and copies entry_context JSON", async () => {
    const entry_context = {
      strategy: "top_signal_entries",
      tp_source: "walk_forward_recommendation",
      walk_forward: {
        gate_source: "grid_meets_target",
        variation: { resolved_tp_win_rate_pct: "92.5" },
      },
    };
    globalThis.fetch = vi.fn(async () =>
      jsonResponse([
        order({
          id: 99,
          symbol: "PTBUSDT",
          entry_context,
          exchange: { ...order().exchange, lifecycle: "closed", lifecycle_label: "Lezárva" },
        }),
      ]),
    ) as unknown as typeof fetch;

    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(globalThis.navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });

    renderOrdersTable();
    const header = await screen.findByRole("button", { name: /PTBUSDT/ });
    await userEvent.click(header);
    expect(screen.getByText(/TPwin=92\.5%/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /JSON másolás/i }));
    expect(writeText).toHaveBeenCalledWith(JSON.stringify(entry_context));
  });
});
