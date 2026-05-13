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

export const REFRESH_INTERVAL_OPTIONS = [5, 10, 15, 30, 60] as const;

export type RefreshIntervalSec = (typeof REFRESH_INTERVAL_OPTIONS)[number];

type Ctx = {
  intervalSec: RefreshIntervalSec;
  setIntervalSec: (v: RefreshIntervalSec) => void;
  options: readonly RefreshIntervalSec[];
};

const RefreshIntervalContext = createContext<Ctx | null>(null);

function isAllowed(n: number): n is RefreshIntervalSec {
  return (REFRESH_INTERVAL_OPTIONS as readonly number[]).includes(n);
}

export function RefreshIntervalProvider({ children }: { children: ReactNode }) {
  const [intervalSec, setState] = useState<RefreshIntervalSec>(10);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const n = parseInt(raw, 10);
    if (isAllowed(n)) setState(n);
  }, []);

  const setIntervalSec = useCallback((v: RefreshIntervalSec) => {
    setState(v);
    if (typeof window !== "undefined") localStorage.setItem(STORAGE_KEY, String(v));
  }, []);

  const value = useMemo(
    () => ({
      intervalSec,
      setIntervalSec,
      options: REFRESH_INTERVAL_OPTIONS,
    }),
    [intervalSec, setIntervalSec],
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
