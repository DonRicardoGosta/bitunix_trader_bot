import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { usePollingQuery } from "./usePollingQuery";

afterEach(() => {
  vi.useRealTimers();
});

describe("usePollingQuery", () => {
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
