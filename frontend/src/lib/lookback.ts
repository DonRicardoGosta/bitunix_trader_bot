/** Dashboard / analytics időablak presetek (órában). */

export const LOOKBACK_PRESETS = [
  { label: "6 óra", hours: 6 },
  { label: "12 óra", hours: 12 },
  { label: "24 óra", hours: 24 },
  { label: "48 óra", hours: 48 },
  { label: "7 nap", hours: 168 },
  { label: "14 nap", hours: 336 },
  { label: "30 nap", hours: 720 },
  { label: "90 nap", hours: 2160 },
] as const;

export function lookbackLabel(hours: number): string {
  const preset = LOOKBACK_PRESETS.find((p) => p.hours === hours);
  return preset?.label ?? `${hours} óra`;
}

export const STORAGE_KEYS = {
  dashboardLookbackHours: "bitunix_ui_dash_lookback_hours",
  analyticsLookbackHours: "bitunix_ui_analytics_lookback_hours",
  analyticsLookbackSelect: "bitunix_ui_analytics_lookback_select",
  analyticsCustomWindowStart: "bitunix_ui_analytics_custom_start",
  analyticsCustomEndMode: "bitunix_ui_analytics_custom_end_mode",
  analyticsCustomWindowEnd: "bitunix_ui_analytics_custom_end",
  analyticsBucketHours: "bitunix_ui_analytics_bucket_hours",
  analyticsTpSlViewMode: "bitunix_ui_analytics_tpsl_view_mode",
  analyticsTpSlWeekday: "bitunix_ui_analytics_tpsl_weekday",
  ordersLookbackHours: "bitunix_ui_orders_lookback_hours",
  ordersRefreshIntervalSec: "bitunix_ui_orders_refresh_interval_sec",
} as const;

export const TP_SL_TIMING_VIEW_MODES = [
  "hours",
  "weekdays",
  "weekday_hours",
] as const;

export type TpSlTimingViewMode = (typeof TP_SL_TIMING_VIEW_MODES)[number];

export function isTpSlTimingViewMode(v: string): v is TpSlTimingViewMode {
  return (TP_SL_TIMING_VIEW_MODES as readonly string[]).includes(v);
}

export function isWeekdayIndex(n: number): boolean {
  return Number.isInteger(n) && n >= 0 && n <= 6;
}

export function isLookbackHours(n: number): boolean {
  return LOOKBACK_PRESETS.some((p) => p.hours === n);
}

export const BUCKET_HOURS_OPTIONS = [1, 6, 12, 24] as const;

export function isBucketHours(n: number): boolean {
  return (BUCKET_HOURS_OPTIONS as readonly number[]).includes(n);
}
