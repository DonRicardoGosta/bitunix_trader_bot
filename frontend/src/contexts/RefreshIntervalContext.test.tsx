import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  RefreshIntervalProvider,
  useRefreshInterval,
} from "./RefreshIntervalContext";

function Consumer() {
  const { intervalSec, setIntervalSec, options } = useRefreshInterval();
  return (
    <div>
      <span data-testid="sec">{intervalSec}</span>
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
    expect(screen.getByTestId("opts").textContent).toBe("5,10,15,30,60");
    await userEvent.click(screen.getByRole("button", { name: "set30" }));
    expect(screen.getByTestId("sec").textContent).toBe("30");
  });
});
