import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act, fireEvent } from "@testing-library/react";
import {
  NavigationLoadingProvider,
  useNavigationLoading,
} from "./NavigationLoadingContext";

const pathnameRef = { current: "/" };

vi.mock("next/navigation", () => ({
  usePathname: () => pathnameRef.current,
}));

function Probe() {
  const { isNavigating, pendingPath, startNavigation } = useNavigationLoading();
  return (
    <div>
      <span data-testid="nav">{isNavigating ? "yes" : "no"}</span>
      <span data-testid="pending">{pendingPath ?? ""}</span>
      <button type="button" onClick={() => startNavigation("/orders")}>
        start
      </button>
    </div>
  );
}

describe("NavigationLoadingProvider", () => {
  beforeEach(() => {
    pathnameRef.current = "/";
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("sets navigating and pending path on internal link click", () => {
    render(
      <NavigationLoadingProvider>
        <a href="/orders">Rendelések</a>
        <Probe />
      </NavigationLoadingProvider>,
    );
    fireEvent.click(screen.getByRole("link", { name: "Rendelések" }), {
      button: 0,
    });
    expect(screen.getByTestId("nav").textContent).toBe("yes");
    expect(screen.getByTestId("pending").textContent).toBe("/orders");
  });

  it("clears navigating after pathname change and minimum delay", () => {
    const { rerender } = render(
      <NavigationLoadingProvider>
        <Probe />
      </NavigationLoadingProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "start" }));
    expect(screen.getByTestId("nav").textContent).toBe("yes");
    pathnameRef.current = "/orders";
    rerender(
      <NavigationLoadingProvider>
        <Probe />
      </NavigationLoadingProvider>,
    );
    act(() => {
      vi.advanceTimersByTime(250);
    });
    expect(screen.getByTestId("nav").textContent).toBe("no");
    expect(screen.getByTestId("pending").textContent).toBe("");
  });
});
