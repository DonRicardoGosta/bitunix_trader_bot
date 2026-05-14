import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { WithRefreshProvider } from "@/contexts/RefreshIntervalContext";
import { useLivePushConnected } from "./LiveUpdatesContext";

function Flag() {
  const on = useLivePushConnected();
  return <span data-testid="live">{on ? "1" : "0"}</span>;
}

describe("LiveUpdatesProvider", () => {
  it("mounts with stub WebSocket (nem nyílik meg valódi kapcsolat)", () => {
    render(
      <WithRefreshProvider>
        <Flag />
      </WithRefreshProvider>,
    );
    expect(screen.getByTestId("live").textContent).toBe("0");
  });
});
