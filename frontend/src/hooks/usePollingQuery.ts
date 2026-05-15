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
 *
 * A korábbi `cancelled` flag + `useEffect` cleanup minta végtelen „Betöltés…”
 * állapotot okozott, ha a reloadKey (pl. orders epoch) gyakrabban változott,
 * mint ahogy a lassú API válaszolt: minden invalidáció megszakította az előző
 * fetch state-frissítését.
 *
 * Itt: egy in-flight kérés, pending jelző gyors invalidációknál, seqRef a
 * elavult válaszok figyelmen kívül hagyására.
 */
export function usePollingQuery<T>(
  fetcher: () => Promise<T>,
  options: Options,
): { data: T | null; error: string | null; isLoading: boolean } {
  const { intervalMs, reloadKey, errorMessage = "Hiba a betöltéskor" } = options;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const seqRef = useRef(0);
  const inFlightRef = useRef(false);
  const pendingRef = useRef(false);

  useEffect(() => {
    async function load() {
      if (inFlightRef.current) {
        pendingRef.current = true;
        return;
      }
      inFlightRef.current = true;
      const mySeq = ++seqRef.current;
      try {
        const result = await fetcherRef.current();
        if (mySeq !== seqRef.current) {
          pendingRef.current = true;
          return;
        }
        setData(result);
        setError(null);
      } catch (err) {
        if (mySeq !== seqRef.current) {
          pendingRef.current = true;
          return;
        }
        setError(err instanceof Error ? err.message : errorMessage);
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
  };
}
