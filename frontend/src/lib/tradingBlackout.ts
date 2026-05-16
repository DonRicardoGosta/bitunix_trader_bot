/** Trading blackout — típusok és nap sorrend (Vezérlőpult). */

export type BlackoutDayMode = "open" | "block_all" | "block_ranges";

export interface BlackoutTimeRange {
  start: string;
  end: string;
}

export interface BlackoutDayConfig {
  mode: BlackoutDayMode;
  block_ranges: BlackoutTimeRange[];
}

export interface TradingBlackoutSchedule {
  timezone: string;
  days: Record<string, BlackoutDayConfig>;
}

export const WEEKDAY_ORDER: { key: string; label: string }[] = [
  { key: "monday", label: "Hétfő" },
  { key: "tuesday", label: "Kedd" },
  { key: "wednesday", label: "Szerda" },
  { key: "thursday", label: "Csütörtök" },
  { key: "friday", label: "Péntek" },
  { key: "saturday", label: "Szombat" },
  { key: "sunday", label: "Vasárnap" },
];

export function defaultTradingBlackoutSchedule(): TradingBlackoutSchedule {
  const days: Record<string, BlackoutDayConfig> = {};
  for (const { key } of WEEKDAY_ORDER) {
    days[key] = { mode: "open", block_ranges: [] };
  }
  return { timezone: "Europe/Budapest", days };
}

/** Normalizál böngésző time input értéket HH:MM-re. */
export function normalizeTimeInput(value: string): string {
  const parts = value.trim().split(":");
  if (parts.length < 2) return value;
  const h = Math.min(23, Math.max(0, Number(parts[0]) || 0));
  const m = Math.min(59, Math.max(0, Number(parts[1]) || 0));
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}
