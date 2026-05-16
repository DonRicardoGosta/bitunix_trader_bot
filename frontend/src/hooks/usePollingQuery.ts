"use client";

import { useEffect, useRef, useState } from "react";

type Options = {
  intervalMs: number;
  /** WebSocket invalidáció / külső jel – azonnali (összevont) újratöltés. */
  reloadKey?: unknown;
  /** Hibaüzenet, ha a fetch nem Error példány. */
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
  /** reloadKey / fetch param változás óta még nem érkezett friss válasz */
  isStale: boolean;
} {
  const { intervalMs, reloadKey, errorMessage = "Hiba a betöltéskor" } = options;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isStale, setIsStale] = useState(false);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const generationRef = useRef(0);
  const inFlightRef = useRef(false);
  const pendingRef = useRef(false);

  useEffect(() => {
    const generation = ++generationRef.current;
    setIsStale(true);

    async function load() {
      if (inFlightRef.current) {
        pendingRef.current = true;
        return;
      }
      inFlightRef.current = true;
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
  }, [intervalMs, reloadKey, errorMessage]);

  return {
    data,
    error,
    isLoading: data === null && error === null,
    isStale,
  };
}
