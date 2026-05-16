import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { usePollingQuery } from "./usePollingQuery";

afterEach(() => {
  vi.useRealTimers();
});

describe("usePollingQuery", () => {
  it("applies first successful result even if reloadKey raced during fetch", async () => {
    let resolveLate: ((v: string) => void) | undefined;
    const fetcher = vi.fn(
      () =>
        new Promise<string>((resolve) => {
          resolveLate = resolve;
        }),
    );

    const { result, rerender } = renderHook(
      ({ key }) =>
        usePollingQuery(fetcher, { intervalMs: 60_000, reloadKey: key }),
      { initialProps: { key: 0 } },
    );

    rerender({ key: 1 });
    rerender({ key: 2 });
    resolveLate?.("done");

    await waitFor(() => expect(result.current.data).toBe("done"), { timeout: 3000 });
  });

  it("eventually resolves when reloadKey changes faster than fetch", async () => {
    let delay = 50;
    const fetcher = vi.fn(
      () =>
        new Promise<string>((resolve) => {
          window.setTimeout(() => resolve("ok"), delay);
          delay = 0;
        }),
    );

    const { result, rerender } = renderHook(
      ({ key }) =>
        usePollingQuery(fetcher, { intervalMs: 60_000, reloadKey: key }),
      { initialProps: { key: 0 } },
    );

    rerender({ key: 1 });
    rerender({ key: 2 });
    rerender({ key: 3 });

    await waitFor(
      () => {
        expect(result.current.data).toBe("ok");
      },
      { timeout: 3000 },
    );
    expect(result.current.error).toBeNull();
  });

  it("debounced reloadKey triggers background refresh", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce("a")
      .mockResolvedValueOnce("b");

    const { result, rerender } = renderHook(
      ({ key }) =>
        usePollingQuery(fetcher, {
          intervalMs: 60_000,
          reloadKey: key,
          reloadDebounceMs: 100,
          staleKey: "fixed",
        }),
      { initialProps: { key: 0 } },
    );

    await waitFor(() => expect(result.current.data).toBe("a"));

    rerender({ key: 1 });
    await waitFor(() => expect(result.current.data).toBe("b"), { timeout: 2000 });
    expect(fetcher.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("marks stale only when staleKey changes", async () => {
    const fetcher = vi.fn().mockResolvedValue("ok");
    const { result, rerender } = renderHook(
      ({ stale }) =>
        usePollingQuery(fetcher, { intervalMs: 60_000, staleKey: stale }),
      { initialProps: { stale: "a" } },
    );

    await waitFor(() => expect(result.current.data).toBe("ok"));
    rerender({ stale: "b" });
    expect(result.current.isStale).toBe(true);
  });

  it("polls on interval", async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn().mockResolvedValue(1);

    renderHook(() => usePollingQuery(fetcher, { intervalMs: 1000 }));

    await act(async () => {
      await Promise.resolve();
    });
    expect(fetcher).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(1000);
      await Promise.resolve();
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
});
