import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OrderForm } from "./OrderForm";

const originalFetch = globalThis.fetch;

beforeEach(() => {
  globalThis.fetch = vi.fn(async () =>
    new Response(
      JSON.stringify({
        client_order_id: "bt-test-1",
        bitunix_order_id: null,
        status: "NEW",
        dry_run: true,
        raw: {},
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  ) as unknown as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("<OrderForm />", () => {
  it("submits with the expected payload and shows dry-run banner", async () => {
    render(<OrderForm />);

    await userEvent.click(screen.getByRole("button", { name: /LONG BTCUSDT/i }));

    await waitFor(() =>
      expect(screen.getByText(/DRY-RUN/i)).toBeInTheDocument(),
    );

    const mock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    expect(mock).toHaveBeenCalledTimes(1);
    const [, init] = mock.mock.calls[0];
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body).toMatchObject({
      symbol: "BTCUSDT",
      side: "BUY",
      orderType: "MARKET",
    });
  });

  it("disables price input for MARKET orders", () => {
    render(<OrderForm />);
    expect(screen.getByLabelText(/Ár \(csak LIMIT\)/i)).toBeDisabled();
  });
});
