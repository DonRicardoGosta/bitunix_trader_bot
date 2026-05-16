/** Analytics egyedi / preset időablak segédek. */

import { LOOKBACK_PRESETS, lookbackLabel } from "@/lib/lookback";

export const ANALYTICS_LOOKBACK_CUSTOM = "custom";

export function isAnalyticsLookbackSelectValue(v: string): boolean {
  if (v === ANALYTICS_LOOKBACK_CUSTOM) return true;
  const h = Number(v);
  return LOOKBACK_PRESETS.some((p) => p.hours === h);
}

export function defaultCustomRangeIso(): { start: string; end: string } {
  const end = new Date();
  const start = new Date(end.getTime() - 24 * 60 * 60 * 1000);
  return { start: start.toISOString(), end: end.toISOString() };
}

/** ``datetime-local`` input érték (böngésző helyi idő). */
export function isoToDatetimeLocalValue(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function datetimeLocalValueToIso(local: string): string | null {
  if (!local.trim()) return null;
  const d = new Date(local);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
}

export function isValidIsoTimestamp(s: string): boolean {
  return Boolean(s) && !Number.isNaN(Date.parse(s));
}

export type AnalyticsQueryParams =
  | { mode: "preset"; lookbackHours: number; bucketHours: number }
  | { mode: "custom"; windowStart: string; windowEnd: string; bucketHours: number };

export function analyticsQueryCacheKey(params: AnalyticsQueryParams): string {
  if (params.mode === "custom") {
    return `custom:${params.windowStart}:${params.windowEnd}:${params.bucketHours}`;
  }
  return `preset:${params.lookbackHours}:${params.bucketHours}`;
}

export function formatAnalyticsWindowDescription(pnl: {
  window_custom?: boolean;
  lookback_hours: number;
  window_start?: string;
  window_end?: string;
}): string {
  if (pnl.window_custom && pnl.window_start && pnl.window_end) {
    return "egyedi ablak";
  }
  return lookbackLabel(pnl.lookback_hours);
}
