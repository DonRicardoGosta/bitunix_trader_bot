"use client";

import { useCallback, useEffect, useMemo } from "react";
import { Input, Select } from "@/components/ui/input";
import {
  ANALYTICS_LOOKBACK_CUSTOM,
  type AnalyticsQueryParams,
  type CustomEndMode,
  analyticsQueryCacheKey,
  datetimeLocalValueToIso,
  defaultCustomStartIso,
  isoToDatetimeLocalValue,
  isAnalyticsLookbackSelectValue,
  isCustomEndMode,
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
  const [lookbackSelect, setLookbackSelect] = usePersistedStringState(
    STORAGE_KEYS.analyticsLookbackSelect,
    "24",
    isAnalyticsLookbackSelectValue,
  );
  const [customStartIso, setCustomStartIso] = usePersistedStringState(
    STORAGE_KEYS.analyticsCustomWindowStart,
    defaultCustomStartIso(),
    isValidIsoTimestamp,
  );
  const [endMode, setEndMode] = usePersistedStringState<CustomEndMode>(
    STORAGE_KEYS.analyticsCustomEndMode,
    "live",
    isCustomEndMode,
  );
  const [customEndIso, setCustomEndIso] = usePersistedStringState(
    STORAGE_KEYS.analyticsCustomWindowEnd,
    new Date().toISOString(),
    isValidIsoTimestamp,
  );

  const isCustom = lookbackSelect === ANALYTICS_LOOKBACK_CUSTOM;
  const endLive = endMode === "live";

  useEffect(() => {
    if (!isCustom) return;
    if (!isValidIsoTimestamp(customStartIso)) {
      setCustomStartIso(defaultCustomStartIso());
    }
    if (!endLive && !isValidIsoTimestamp(customEndIso)) {
      setCustomEndIso(new Date().toISOString());
    }
  }, [isCustom, customStartIso, customEndIso, endLive, setCustomStartIso, setCustomEndIso]);

  const params: AnalyticsQueryParams = useMemo(() => {
    if (isCustom) {
      return {
        mode: "custom",
        windowStart: customStartIso,
        endLive,
        windowEnd: endLive ? undefined : customEndIso,
        bucketHours,
      };
    }
    const h = Number(lookbackSelect);
    const lookbackHours = LOOKBACK_PRESETS.some((p) => p.hours === h) ? h : 24;
    return { mode: "preset", lookbackHours, bucketHours };
  }, [isCustom, customStartIso, endLive, customEndIso, lookbackSelect, bucketHours]);

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
            <label className="block text-xs uppercase text-muted mb-1" htmlFor="an-custom-end-mode">
              Vége
            </label>
            <Select
              id="an-custom-end-mode"
              value={endMode}
              onChange={(e) => {
                const v = e.target.value;
                if (isCustomEndMode(v)) setEndMode(v);
              }}
            >
              <option value="live">Most (élő)</option>
              <option value="fixed">Fix időpont</option>
            </Select>
          </div>
          {!endLive ? (
            <div>
              <label
                className="block text-xs uppercase text-muted mb-1"
                htmlFor="an-custom-end"
              >
                Vége időpontja
              </label>
              <Input
                id="an-custom-end"
                type="datetime-local"
                value={isoToDatetimeLocalValue(customEndIso)}
                onChange={(e) => onEndLocal(e.target.value)}
                className="min-w-[12.5rem]"
              />
            </div>
          ) : null}
        </>
      ) : null}
    </>
  );

  return { params, cacheKey, isCustom, controls };
}
