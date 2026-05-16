"use client";

import { useCallback, useEffect, useMemo } from "react";
import { Input, Select } from "@/components/ui/input";
import {
  ANALYTICS_LOOKBACK_CUSTOM,
  type AnalyticsQueryParams,
  analyticsQueryCacheKey,
  datetimeLocalValueToIso,
  defaultCustomRangeIso,
  isoToDatetimeLocalValue,
  isAnalyticsLookbackSelectValue,
  isValidIsoTimestamp,
} from "@/lib/analyticsWindow";
import { LOOKBACK_PRESETS, STORAGE_KEYS } from "@/lib/lookback";
import { usePersistedStringState } from "@/hooks/usePersistedState";

export function useAnalyticsWindowQuery(bucketHours: number): {
  params: AnalyticsQueryParams;
  cacheKey: string;
  isCustom: boolean;
  controls: React.ReactNode;
} {
  const defaults = useMemo(() => defaultCustomRangeIso(), []);
  const [lookbackSelect, setLookbackSelect] = usePersistedStringState(
    STORAGE_KEYS.analyticsLookbackSelect,
    "24",
    isAnalyticsLookbackSelectValue,
  );
  const [customStartIso, setCustomStartIso] = usePersistedStringState(
    STORAGE_KEYS.analyticsCustomWindowStart,
    defaults.start,
    isValidIsoTimestamp,
  );
  const [customEndIso, setCustomEndIso] = usePersistedStringState(
    STORAGE_KEYS.analyticsCustomWindowEnd,
    defaults.end,
    isValidIsoTimestamp,
  );

  const isCustom = lookbackSelect === ANALYTICS_LOOKBACK_CUSTOM;

  useEffect(() => {
    if (!isCustom) return;
    if (!isValidIsoTimestamp(customStartIso) || !isValidIsoTimestamp(customEndIso)) {
      const d = defaultCustomRangeIso();
      setCustomStartIso(d.start);
      setCustomEndIso(d.end);
    }
  }, [isCustom, customStartIso, customEndIso, setCustomStartIso, setCustomEndIso]);

  const params: AnalyticsQueryParams = useMemo(() => {
    if (isCustom) {
      return {
        mode: "custom",
        windowStart: customStartIso,
        windowEnd: customEndIso,
        bucketHours,
      };
    }
    const h = Number(lookbackSelect);
    const lookbackHours = LOOKBACK_PRESETS.some((p) => p.hours === h) ? h : 24;
    return { mode: "preset", lookbackHours, bucketHours };
  }, [isCustom, customStartIso, customEndIso, lookbackSelect, bucketHours]);

  const cacheKey = analyticsQueryCacheKey(params);

  const onStartLocal = useCallback(
    (local: string) => {
      const iso = datetimeLocalValueToIso(local);
      if (iso) setCustomStartIso(iso);
    },
    [setCustomStartIso],
  );

  const onEndLocal = useCallback(
    (local: string) => {
      const iso = datetimeLocalValueToIso(local);
      if (iso) setCustomEndIso(iso);
    },
    [setCustomEndIso],
  );

  const controls = (
    <>
      <div>
        <label className="block text-xs uppercase text-muted mb-1" htmlFor="an-lb">
          Ablak
        </label>
        <Select
          id="an-lb"
          value={lookbackSelect}
          onChange={(e) => setLookbackSelect(e.target.value)}
        >
          {LOOKBACK_PRESETS.map((p) => (
            <option key={p.hours} value={String(p.hours)}>
              {p.label}
            </option>
          ))}
          <option value={ANALYTICS_LOOKBACK_CUSTOM}>Egyedi…</option>
        </Select>
      </div>
      {isCustom ? (
        <>
          <div>
            <label className="block text-xs uppercase text-muted mb-1" htmlFor="an-custom-start">
              Kezdete
            </label>
            <Input
              id="an-custom-start"
              type="datetime-local"
              value={isoToDatetimeLocalValue(customStartIso)}
              onChange={(e) => onStartLocal(e.target.value)}
              className="min-w-[12.5rem]"
            />
          </div>
          <div>
            <label className="block text-xs uppercase text-muted mb-1" htmlFor="an-custom-end">
              Vége
            </label>
            <Input
              id="an-custom-end"
              type="datetime-local"
              value={isoToDatetimeLocalValue(customEndIso)}
              onChange={(e) => onEndLocal(e.target.value)}
              className="min-w-[12.5rem]"
            />
          </div>
        </>
      ) : null}
    </>
  );

  return { params, cacheKey, isCustom, controls };
}

// fix div typo - should be div
