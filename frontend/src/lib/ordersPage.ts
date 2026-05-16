/** Rendelések oldal – saját frissítési intervallum (nem a globális Navbar). */

import { LOOKBACK_PRESETS } from "@/lib/lookback";

/** 0 = nincs időszűrés (legutóbbi 500 sor, mint a main ágon). */
export const ORDERS_LOOKBACK_PRESETS = [
  { label: "Legutóbbi 500", hours: 0 },
  ...LOOKBACK_PRESETS,
] as const;

export function isOrdersLookbackHours(n: number): boolean {
  return ORDERS_LOOKBACK_PRESETS.some((p) => p.hours === n);
}

export function ordersLookbackLabel(hours: number): string {
  const preset = ORDERS_LOOKBACK_PRESETS.find((p) => p.hours === hours);
  return preset?.label ?? `${hours} óra`;
}

export const ORDERS_REFRESH_INTERVAL_OPTIONS = [30, 60, 120, 300] as const;

export type OrdersRefreshIntervalSec =
  (typeof ORDERS_REFRESH_INTERVAL_OPTIONS)[number];

export const ORDERS_LIFECYCLE_CLOSED = "closed" as const;

export function isOrdersRefreshIntervalSec(n: number): n is OrdersRefreshIntervalSec {
  return (ORDERS_REFRESH_INTERVAL_OPTIONS as readonly number[]).includes(n);
}

export function ordersRefreshLabel(sec: number): string {
  if (sec < 60) return `${sec} mp`;
  if (sec % 60 === 0) return `${sec / 60} perc`;
  return `${sec} mp`;
}
