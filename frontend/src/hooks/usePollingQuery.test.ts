import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { usePollingQuery } from "./usePollingQuery";

afterEach(() => {
  vi.useRealTimers();
});

describe("usePollingQuery", () => {
  it("eventually resolves when reloadKey changes faster than fetch", async () => {
    let resolveFetch: ((v: string) => void) | undefined;
    const fetcher = vi.fn(
      () =>
        new Promise<string>((resolve) => {
          resolveFetch = resolve;
        }),
    );

    const { result, rerender } = renderHook(
      ({ key }) =>
        usePollingQuery(fetcher, { intervalMs: 60_000, reloadKey: key }),
      { initialProps: { key: 0 } },
    );

    expect(result.current.isLoading).toBe(true);

    rerender({ key: 1 });
    rerender({ key: 2 });
    rerender({ key: 3 });

    expect(fetcher).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveFetch!("ok");
    });

    await waitFor(() => {
      expect(result.current.data).toBe("ok");
    });
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
