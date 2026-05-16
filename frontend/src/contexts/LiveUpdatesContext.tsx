"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { liveStreamWebSocketUrl } from "@/lib/api";

/** Megegyezik a backend ``DEFAULT_INVALIDATION_TOPICS`` sorrendjével / tartalmával. */
export const LIVE_TOPICS = [
  "dashboard",
  "orders",
  "orders_pnl",
  "positions",
  "calibration",
  "strategies",
  "events",
  "market",
  "settings",
  "analytics",
] as const;

export type LiveTopic = (typeof LIVE_TOPICS)[number];

const TOPIC_SET = new Set<string>(LIVE_TOPICS);

type Ctx = {
  /** Van nyitott WebSocket (Navbar); a REST polling ettől függetlenül fut tovább. */
  pushConnected: boolean;
  /** Adott szekció epochja: invalidációkor nő → useEffect(refetch). */
  epochFor(topic: LiveTopic): number;
};

const LiveUpdatesContext = createContext<Ctx | null>(null);

function bumpTopics(
  prev: Record<string, number>,
  topics: readonly string[],
): Record<string, number> {
  const next = { ...prev };
  for (const t of topics) {
    if (TOPIC_SET.has(t)) {
      next[t] = (next[t] ?? 0) + 1;
    }
  }
  return next;
}

export function LiveUpdatesProvider({ children }: { children: ReactNode }) {
  const [epochs, setEpochs] = useState<Record<string, number>>({});
  const [pushConnected, setPushConnected] = useState(false);
  const reconnectAttempt = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);
  const stoppedRef = useRef(false);

  const epochFor = useCallback(
    (topic: LiveTopic) => epochs[topic] ?? 0,
    [epochs],
  );

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    /** Strict Mode: első mount cleanup lefut, mielőtt a WS megnyílna — a régi handler ne állítson state-et. */
    let active = true;
    stoppedRef.current = false;

    const scheduleReconnect = (fn: () => void, delayMs: number) =>
      window.setTimeout(fn, delayMs);

    const connect = () => {
      if (!active || stoppedRef.current) return;
      const url = liveStreamWebSocketUrl();
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!active || wsRef.current !== ws) return;
        reconnectAttempt.current = 0;
        setPushConnected(true);
      };

      ws.onmessage = (ev) => {
        if (!active || wsRef.current !== ws) return;
        try {
          const raw = typeof ev.data === "string" ? ev.data : "";
          const msg = JSON.parse(raw) as { type?: string; topics?: unknown };
          if (msg.type !== "invalidate" || !Array.isArray(msg.topics)) return;
          setEpochs((p) => bumpTopics(p, msg.topics as string[]));
        } catch {
          /* ignore malformed */
        }
      };

      ws.onerror = () => {
        if (!active || wsRef.current !== ws) return;
        setPushConnected(false);
      };

      ws.onclose = () => {
        if (wsRef.current === ws) wsRef.current = null;
        if (!active) return;
        setPushConnected(false);
        if (stoppedRef.current) return;
        const n = reconnectAttempt.current;
        reconnectAttempt.current = n + 1;
        const delay = Math.min(30_000, 1000 * 2 ** Math.min(n, 5));
        scheduleReconnect(connect, delay);
      };
    };

    connect();

    return () => {
      active = false;
      stoppedRef.current = true;
      wsRef.current?.close();
      wsRef.current = null;
      setPushConnected(false);
    };
  }, []);

  const value = useMemo(
    () => ({
      pushConnected,
      epochFor,
    }),
    [pushConnected, epochFor],
  );

  return (
    <LiveUpdatesContext.Provider value={value}>{children}</LiveUpdatesContext.Provider>
  );
}

export function useLiveUpdates(): Ctx {
  const c = useContext(LiveUpdatesContext);
  if (!c) {
    throw new Error("useLiveUpdates must be used within LiveUpdatesProvider");
  }
  return c;
}

/** Csak epoch (provider nélküli teszteknél használj mockot). */
export function useLiveEpoch(topic: LiveTopic): number {
  return useLiveUpdates().epochFor(topic);
}

export function useLivePushConnected(): boolean {
  return useLiveUpdates().pushConnected;
}

/** Tesztekhez provider nélküli ág elkerülése. */
export function WithLiveUpdatesProvider({ children }: { children: ReactNode }) {
  return <LiveUpdatesProvider>{children}</LiveUpdatesProvider>;
}
