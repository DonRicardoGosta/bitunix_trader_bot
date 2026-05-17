"use client";

import { useMemo } from "react";
import { api } from "@/lib/api";
import { useLiveEpoch } from "@/contexts/LiveUpdatesContext";
import { usePollingQuery } from "@/hooks/usePollingQuery";

/** Egy API hívás: rendeléslista + PnL (közös backend enrichment). */
export function useOrdersBundle(lookbackHours: number, refreshIntervalMs: number) {
  const ordersEpoch = useLiveEpoch("orders");
  const pnlEpoch = useLiveEpoch("orders_pnl");
  const reloadKey = useMemo(
    () => `${ordersEpoch}:${pnlEpoch}`,
    [ordersEpoch, pnlEpoch],
  );

  return usePollingQuery(
    () => api.ordersBundle(lookbackHours, 500),
    {
      intervalMs: refreshIntervalMs,
      reloadKey,
      reloadDebounceMs: 1500,
      staleKey: `${lookbackHours}:${refreshIntervalMs}`,
      errorMessage: "Rendelések betöltése sikertelen",
    },
  );
}
