"use client";

import { useEffect, useRef, useState } from "react";

type Options = {
  intervalMs: number;
  /** WebSocket invalidáció / külső jel – azonnali újratöltés. */
  reloadKey?: unknown;
  /**
   * Ha megadva: „stale” csak ennek változásakor (pl. lookback), nem interval/WS miatt.
   * Így a háttér-frissítés nem sötétíti le az egész oldalt.
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
  /** Paraméterváltás óta még nincs új válasz (nem használ teljes oldal dimmelést). */
  isStale: boolean;
  /** Háttér-frissítés fut (már van adat) – diszkrét jelzéshez. */
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

  const generationRef = useRef(0);
  const inFlightRef = useRef(false);
  const pendingRef = useRef(false);
  const prevStaleKeyRef = useRef(staleKey);
  const hasDataRef = useRef(false);
  hasDataRef.current = data !== null;

  useEffect(() => {
    if (staleKey !== undefined && staleKey !== prevStaleKeyRef.current) {
      prevStaleKeyRef.current = staleKey;
      setIsStale(true);
    }

    const generation = ++generationRef.current;

    async function load() {
      if (inFlightRef.current) {
        pendingRef.current = true;
        return;
      }
      inFlightRef.current = true;
      if (hasDataRef.current) {
        setIsRefreshing(true);
      }
      const startedGen = generationRef.current;
      try {
        const result = await fetcherRef.current();
        if (startedGen !== generationRef.current) {
          pendingRef.current = true;
          return;
        }
        setData(result);
        setError(null);
        setIsStale(false);
      } catch (err) {
        if (startedGen !== generationRef.current) {
          pendingRef.current = true;
          return;
        }
        setError(err instanceof Error ? err.message : errorMessage);
        setIsStale(false);
      } finally {
        inFlightRef.current = false;
        setIsRefreshing(false);
        if (pendingRef.current) {
          pendingRef.current = false;
          void load();
        }
      }
    }

    void load();
    const id =
      intervalMs > 0 ? window.setInterval(() => void load(), intervalMs) : undefined;
    return () => {
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
