import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EventsPage from "./page";
import { WithRefreshProvider } from "@/contexts/RefreshIntervalContext";

const originalFetch = globalThis.fetch;

function jsonResponse(data: unknown) {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

let lastUrl = "";

beforeEach(() => {
  lastUrl = "";
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    lastUrl = url;
    return jsonResponse([
      {
        id: 1,
        level: "INFO",
        event: "strategy.top_movers.ranked",
        message: "Top 3 mover kiválasztva.",
        payload: null,
        strategy_name: "top_movers",
        created_at: "2026-05-13T10:00:00Z",
      },
      {
        id: 2,
        level: "ERROR",
        event: "strategy.top_movers.leverage_error",
        message: "boom",
        payload: null,
        strategy_name: "top_movers",
        created_at: "2026-05-13T10:00:05Z",
      },
    ]);
  }) as unknown as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("<EventsPage />", () => {
  it("lists events with level badges", async () => {
    render(
      <WithRefreshProvider>
        <EventsPage />
      </WithRefreshProvider>,
    );
    await waitFor(() =>
      expect(screen.getByText("strategy.top_movers.ranked")).toBeInTheDocument(),
    );
    // INFO és ERROR is megjelenik a select option-okben + a badge-en is.
    // A táblázat sorának INFO/ERROR badge-ét keressük span elem alapján.
    const badges = screen.getAllByText(/^(INFO|ERROR)$/);
    expect(badges.some((el) => el.tagName.toLowerCase() === "span" && el.textContent === "INFO")).toBe(true);
    expect(badges.some((el) => el.tagName.toLowerCase() === "span" && el.textContent === "ERROR")).toBe(true);
    expect(
      screen.getByText("strategy.top_movers.leverage_error"),
    ).toBeInTheDocument();
  });

  it("applies level filter to API call", async () => {
    render(
      <WithRefreshProvider>
        <EventsPage />
      </WithRefreshProvider>,
    );
    await screen.findByText("strategy.top_movers.ranked");
    await userEvent.selectOptions(screen.getByLabelText(/Szint/i), "ERROR");
    await waitFor(() => expect(lastUrl).toContain("level=ERROR"));
  });
});
