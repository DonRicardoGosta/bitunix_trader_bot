"use client";

import { useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { StatCard } from "@/components/ui/StatCard";
import { PnlSeriesChart } from "@/components/PnlSeriesChart";
import { api, type PnlSeriesResponse } from "@/lib/api";
import { LOOKBACK_PRESETS, lookbackLabel } from "@/lib/lookback";
import { useRefreshInterval } from "@/contexts/RefreshIntervalContext";
import { useLiveEpoch } from "@/contexts/LiveUpdatesContext";
import { usePollingQuery } from "@/hooks/usePollingQuery";
import { formatNumber } from "@/lib/utils";

const BUCKET_OPTIONS = [
  { label: "1 óra", hours: 1 },
  { label: "6 óra", hours: 6 },
  { label: "12 óra", hours: 12 },
  { label: "24 óra", hours: 24 },
] as const;

function toneOf(n: number): "positive" | "negative" | "neutral" {
  if (n > 0) return "positive";
  if (n < 0) return "negative";
  return "neutral";
}

export default function AnalyticsPage() {
  const { refreshIntervalMs } = useRefreshInterval();
  const analyticsEpoch = useLiveEpoch("analytics");
  const [lookbackHours, setLookbackHours] = useState(168);
  const [bucketHours, setBucketHours] = useState(6);

  const { data, error } = usePollingQuery(
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

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Analytics</h1>
          <p className="text-muted text-sm mt-1">
            Lezárt pozíciók realized PnL — {lookbackLabel(lookbackHours)}
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="block text-xs uppercase text-muted mb-1" htmlFor="an-lb">
              Ablak
            </label>
            <Select
              id="an-lb"
              value={lookbackHours}
              onChange={(e) => setLookbackHours(Number(e.target.value) || 168)}
            >
              {LOOKBACK_PRESETS.map((p) => (
                <option key={p.hours} value={p.hours}>
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
              value={bucketHours}
              onChange={(e) => setBucketHours(Number(e.target.value) || 6)}
            >
              {BUCKET_OPTIONS.map((p) => (
                <option key={p.hours} value={p.hours}>
                  {p.label}
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
              <PnlSeriesChart data={data} />
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
