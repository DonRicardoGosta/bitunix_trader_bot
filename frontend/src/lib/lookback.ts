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
  analyticsBucketHours: "bitunix_ui_analytics_bucket_hours",
} as const;

export function isLookbackHours(n: number): boolean {
  return LOOKBACK_PRESETS.some((p) => p.hours === n);
}

export const BUCKET_HOURS_OPTIONS = [1, 6, 12, 24] as const;

export function isBucketHours(n: number): boolean {
  return (BUCKET_HOURS_OPTIONS as readonly number[]).includes(n);
}
