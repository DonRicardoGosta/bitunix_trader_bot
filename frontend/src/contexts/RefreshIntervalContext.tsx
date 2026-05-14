"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

const STORAGE_KEY = "bitunix_trader_ui_refresh_interval_sec";

/** Rejtett lapon ritkább polling: kevesebb API/DB terhelés, kevesebb akkumulátorhasználat. */
const VISIBILITY_SLOWDOWN_MULT = 4;
const MAX_BACKGROUND_INTERVAL_MS = 120_000;

export function backgroundAwareIntervalMs(baseMs: number, documentHidden: boolean): number {
  if (!documentHidden || baseMs <= 0) return baseMs;
  return Math.min(MAX_BACKGROUND_INTERVAL_MS, baseMs * VISIBILITY_SLOWDOWN_MULT);
}

export const REFRESH_INTERVAL_OPTIONS = [5, 10, 15, 30, 60] as const;

export type RefreshIntervalSec = (typeof REFRESH_INTERVAL_OPTIONS)[number];

type Ctx = {
  intervalSec: RefreshIntervalSec;
  /** Valós `setInterval` késleltetés ms-ban; háttérben automatikusan ritkább. */
  refreshIntervalMs: number;
  setIntervalSec: (v: RefreshIntervalSec) => void;
  options: readonly RefreshIntervalSec[];
};

const RefreshIntervalContext = createContext<Ctx | null>(null);

function isAllowed(n: number): n is RefreshIntervalSec {
  return (REFRESH_INTERVAL_OPTIONS as readonly number[]).includes(n);
}

export function RefreshIntervalProvider({ children }: { children: ReactNode }) {
  const [intervalSec, setState] = useState<RefreshIntervalSec>(10);
  const [documentHidden, setDocumentHidden] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const n = parseInt(raw, 10);
    if (isAllowed(n)) setState(n);
  }, []);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const sync = () => setDocumentHidden(document.hidden);
    sync();
    document.addEventListener("visibilitychange", sync);
    return () => document.removeEventListener("visibilitychange", sync);
  }, []);

  const setIntervalSec = useCallback((v: RefreshIntervalSec) => {
    setState(v);
    if (typeof window !== "undefined") localStorage.setItem(STORAGE_KEY, String(v));
  }, []);

  const refreshIntervalMs = useMemo(
    () => backgroundAwareIntervalMs(intervalSec * 1000, documentHidden),
    [intervalSec, documentHidden],
  );

  const value = useMemo(
    () => ({
      intervalSec,
      refreshIntervalMs,
      setIntervalSec,
      options: REFRESH_INTERVAL_OPTIONS,
    }),
    [intervalSec, refreshIntervalMs, setIntervalSec],
  );

  return (
    <RefreshIntervalContext.Provider value={value}>{children}</RefreshIntervalContext.Provider>
  );
}

export function useRefreshInterval(): Ctx {
  const c = useContext(RefreshIntervalContext);
  if (!c) {
    throw new Error("useRefreshInterval must be used within RefreshIntervalProvider");
  }
  return c;
}

/** Tesztekhez: provider nélküli render elkerülése. */
export function WithRefreshProvider({ children }: { children: ReactNode }) {
  return <RefreshIntervalProvider>{children}</RefreshIntervalProvider>;
}
