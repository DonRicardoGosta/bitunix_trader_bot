"use client";

import { useEffect, useRef, useState } from "react";

type Options = {
  intervalMs: number;
  /** WebSocket invalidáció / külső jel – azonnali újratöltés. */
  reloadKey?: unknown;
  /**
   * Ha megadva: „stale” csak ennek változásakor (pl. lookback), nem interval/WS miatt.
   */
  staleKey?: unknown;
  errorMessage?: string;
};

/**
 * Időzített + eseményvezérelt REST betöltés élő UI-hoz.
 */
export function usePollingQuery<T>(
  fetcher: () => Promise<T>,
  options: Options,
): {
  data: T | null;
  error: string | null;
  isLoading: boolean;
  isStale: boolean;
  isRefreshing: boolean;
} {
  const {
    intervalMs,
    reloadKey,
    staleKey,
    errorMessage = "Hiba a betöltéskor",
  } = options;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isStale, setIsStale] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const hasDataRef = useRef(false);
  hasDataRef.current = data !== null;
  const prevStaleKeyRef = useRef(staleKey);

  useEffect(() => {
    if (staleKey !== undefined && staleKey !== prevStaleKeyRef.current) {
      prevStaleKeyRef.current = staleKey;
      setIsStale(true);
    }

    let active = true;
    let inFlight = false;
    let pending = false;

    async function load() {
      if (!active) return;
      if (inFlight) {
        pending = true;
        return;
      }
      inFlight = true;
      if (hasDataRef.current) {
        setIsRefreshing(true);
      }
      try {
        const result = await fetcherRef.current();
        if (!active) return;
        setData(result);
        setError(null);
        setIsStale(false);
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : errorMessage);
        setIsStale(false);
      } finally {
        inFlight = false;
        if (active) {
          setIsRefreshing(false);
        }
        if (pending && active) {
          pending = false;
          void load();
        }
      }
    }

    void load();
    const id =
      intervalMs > 0 ? window.setInterval(() => void load(), intervalMs) : undefined;
    return () => {
      active = false;
      if (id !== undefined) window.clearInterval(id);
    };
  }, [intervalMs, reloadKey, staleKey, errorMessage]);

  return {
    data,
    error,
    isLoading: data === null && error === null,
    isStale,
    isRefreshing,
  };
}
