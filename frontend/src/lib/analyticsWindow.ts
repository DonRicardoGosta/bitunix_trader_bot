/** Analytics egyedi / preset időablak segédek. */

import { LOOKBACK_PRESETS, lookbackLabel } from "@/lib/lookback";

export const ANALYTICS_LOOKBACK_CUSTOM = "custom";

export const CUSTOM_END_MODES = ["live", "fixed"] as const;
export type CustomEndMode = (typeof CUSTOM_END_MODES)[number];

export function isCustomEndMode(v: string): v is CustomEndMode {
  return (CUSTOM_END_MODES as readonly string[]).includes(v);
}

export function isAnalyticsLookbackSelectValue(v: string): boolean {
  if (v === ANALYTICS_LOOKBACK_CUSTOM) return true;
  const h = Number(v);
  return LOOKBACK_PRESETS.some((p) => p.hours === h);
}

export function defaultCustomStartIso(): string {
  const end = new Date();
  const start = new Date(end.getTime() - 24 * 60 * 60 * 1000);
  return start.toISOString();
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
  | {
      mode: "custom";
      windowStart: string;
      endLive: boolean;
      windowEnd?: string;
      bucketHours: number;
    };

export function analyticsQueryCacheKey(params: AnalyticsQueryParams): string {
  if (params.mode === "custom") {
    if (params.endLive) {
      return `custom:${params.windowStart}:live:${params.bucketHours}`;
    }
    return `custom:${params.windowStart}:${params.windowEnd ?? ""}:${params.bucketHours}`;
  }
  return `preset:${params.lookbackHours}:${params.bucketHours}`;
}

export function formatAnalyticsWindowDescription(pnl: {
  window_custom?: boolean;
  window_end_live?: boolean;
  lookback_hours: number;
  window_start?: string;
}): string {
  if (pnl.window_custom) {
    return pnl.window_end_live ? "egyedi (élő vég)" : "egyedi ablak";
  }
  return lookbackLabel(pnl.lookback_hours);
}

export function formatCustomWindowRangeLabel(
  startIso?: string,
  endIso?: string,
  endLive?: boolean,
): string | null {
  if (!startIso) return null;
  const fmt = (iso: string) =>
    new Date(iso).toLocaleString("hu-HU", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  if (endLive) {
    return `${fmt(startIso)} – most`;
  }
  if (endIso) {
    return `${fmt(startIso)} – ${fmt(endIso)}`;
  }
  return fmt(startIso);
}
