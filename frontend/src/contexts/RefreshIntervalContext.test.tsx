import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  RefreshIntervalProvider,
  useRefreshInterval,
  backgroundAwareIntervalMs,
} from "./RefreshIntervalContext";

function Consumer() {
  const { intervalSec, refreshIntervalMs, setIntervalSec, options } = useRefreshInterval();
  return (
    <div>
      <span data-testid="sec">{intervalSec}</span>
      <span data-testid="ms">{refreshIntervalMs}</span>
      <button type="button" onClick={() => setIntervalSec(30)}>
        set30
      </button>
      <span data-testid="opts">{options.join(",")}</span>
    </div>
  );
}

describe("RefreshIntervalProvider", () => {
  it("defaults to 10 seconds and updates selection", async () => {
    render(
      <RefreshIntervalProvider>
        <Consumer />
      </RefreshIntervalProvider>,
    );
    expect(screen.getByTestId("sec").textContent).toBe("10");
    expect(screen.getByTestId("ms").textContent).toBe("10000");
    expect(screen.getByTestId("opts").textContent).toBe("5,10,15,30,60");
    await userEvent.click(screen.getByRole("button", { name: "set30" }));
    expect(screen.getByTestId("sec").textContent).toBe("30");
    expect(screen.getByTestId("ms").textContent).toBe("30000");
  });
});

describe("backgroundAwareIntervalMs", () => {
  it("leaves interval unchanged when tab is visible", () => {
    expect(backgroundAwareIntervalMs(10_000, false)).toBe(10_000);
  });

  it("slows down when tab is hidden, capped", () => {
    expect(backgroundAwareIntervalMs(10_000, true)).toBe(40_000);
    expect(backgroundAwareIntervalMs(60_000, true)).toBe(120_000);
  });
});
