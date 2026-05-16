"use client";

import { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { StatCard } from "@/components/ui/StatCard";
import { PnlSeriesChart } from "@/components/PnlSeriesChart";
import { api, type PnlSeriesResponse } from "@/lib/api";
import { usePersistedState } from "@/hooks/usePersistedState";
import {
  BUCKET_HOURS_OPTIONS,
  LOOKBACK_PRESETS,
  STORAGE_KEYS,
  isBucketHours,
  isLookbackHours,
  lookbackLabel,
} from "@/lib/lookback";
import { useRefreshInterval } from "@/contexts/RefreshIntervalContext";
import { useLiveEpoch } from "@/contexts/LiveUpdatesContext";
import { usePollingQuery } from "@/hooks/usePollingQuery";
import { cn, formatNumber } from "@/lib/utils";

const BUCKET_LABELS: Record<number, string> = {
  1: "1 óra",
  6: "6 óra",
  12: "12 óra",
  24: "24 óra",
};

function toneOf(n: number): "positive" | "negative" | "neutral" {
  if (n > 0) return "positive";
  if (n < 0) return "negative";
  return "neutral";
}

export default function AnalyticsPage() {
  const { refreshIntervalMs } = useRefreshInterval();
  const analyticsEpoch = useLiveEpoch("analytics");
  const [lookbackHours, setLookbackHours] = usePersistedState(
    STORAGE_KEYS.analyticsLookbackHours,
    168,
    isLookbackHours,
  );
  const [bucketHours, setBucketHours] = usePersistedState(
    STORAGE_KEYS.analyticsBucketHours,
    6,
    isBucketHours,
  );

  const { data, error, isStale } = usePollingQuery(
    () => api.analyticsPnlSeries(lookbackHours, bucketHours),
    {
      intervalMs: refreshIntervalMs,
      reloadKey: `${analyticsEpoch}:${lookbackHours}:${bucketHours}`,
      errorMessage: "Analytics betöltési hiba",
    },
  );

  const kpis = data?.kpis;
  const realized = useMemo(
    () => (kpis ? Number(kpis.realized_pnl_usdt) : 0),
    [kpis],
  );

  const chartKey = data
    ? `${data.lookback_hours}:${data.bucket_hours}:${data.buckets.length}:${data.cumulative.length}`
    : "empty";

  return (
    <div
      className={cn(
        "space-y-6 transition-opacity",
        isStale && "opacity-70",
      )}
    >
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Analytics</h1>
          <p className="text-muted text-sm mt-1">
            Lezárt pozíciók realized PnL
            {data
              ? ` · API ablak: ${lookbackLabel(data.lookback_hours)}, bucket ${data.bucket_hours}h`
              : ` · ${lookbackLabel(lookbackHours)}`}
            {isStale ? " · frissítés…" : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="block text-xs uppercase text-muted mb-1" htmlFor="an-lb">
              Ablak
            </label>
            <Select
              id="an-lb"
              value={String(lookbackHours)}
              onChange={(e) => setLookbackHours(Number(e.target.value) || 168)}
            >
              {LOOKBACK_PRESETS.map((p) => (
                <option key={p.hours} value={String(p.hours)}>
                  {p.label}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label className="block text-xs uppercase text-muted mb-1" htmlFor="an-bk">
              Bucket
            </label>
            <Select
              id="an-bk"
              value={String(bucketHours)}
              onChange={(e) => setBucketHours(Number(e.target.value) || 6)}
            >
              {BUCKET_HOURS_OPTIONS.map((h) => (
                <option key={h} value={String(h)}>
                  {BUCKET_LABELS[h] ?? `${h} óra`}
                </option>
              ))}
            </Select>
          </div>
        </div>
      </header>

      {error && <p className="text-loss text-sm">{error}</p>}
      {!data && !error && <p className="text-muted text-sm">Betöltés…</p>}

      {data && kpis && (
        <>
          <KpiRow data={data} realized={realized} />
          <Card>
            <CardHeader>
              <CardTitle>PnL idősor</CardTitle>
              {data.sync_error && (
                <span className="text-xs text-amber-400">{data.sync_error}</span>
              )}
            </CardHeader>
            <CardContent>
              <PnlSeriesChart key={chartKey} data={data} />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function KpiRow({
  data,
  realized,
}: {
  data: PnlSeriesResponse;
  realized: number;
}) {
  const k = data.kpis;
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-6 gap-3">
      <StatCard
        label="Realized PnL"
        value={formatNumber(realized, { decimals: 4, sign: true })}
        unit="USDT"
        tone={toneOf(realized)}
      />
      <StatCard
        label="Win rate"
        value={k.win_rate_pct ?? "—"}
        unit={k.win_rate_pct ? "%" : ""}
      />
      <StatCard label="Pozíciók" value={String(k.count)} unit="db" />
      <StatCard
        label="Profit factor"
        value={k.profit_factor ?? "—"}
        hint="gross win / gross loss"
      />
      <StatCard
        label="Expectancy"
        value={k.expectancy_usdt ?? "—"}
        unit="USDT / trade"
      />
      <StatCard
        label="Max drawdown"
        value={formatNumber(k.max_drawdown_usdt, { decimals: 4 })}
        unit="USDT"
        tone="negative"
      />
    </div>
  );
}
