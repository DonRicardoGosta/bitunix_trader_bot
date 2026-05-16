"use client";

import { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { StatCard } from "@/components/ui/StatCard";
import { PnlSeriesChart } from "@/components/PnlSeriesChart";
import { TpSlByHourChart } from "@/components/TpSlByHourChart";
import { AnalyticsBreakdown } from "@/components/AnalyticsBreakdown";
import { AnalyticsDbPanels } from "@/components/AnalyticsDbPanels";
import { RefreshIndicator } from "@/components/RefreshIndicator";
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
import { formatNumber } from "@/lib/utils";

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

function formatWindow(iso?: string): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("hu-HU", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function AnalyticsPage() {
  const { refreshIntervalMs } = useRefreshInterval();
  const analyticsEpoch = useLiveEpoch("analytics");
  const [lookbackHours, setLookbackHours] = usePersistedState(
    STORAGE_KEYS.analyticsLookbackHours,
    24,
    isLookbackHours,
  );
  const [bucketHours, setBucketHours] = usePersistedState(
    STORAGE_KEYS.analyticsBucketHours,
    6,
    isBucketHours,
  );

  const paramKey = `${lookbackHours}:${bucketHours}`;

  const { data, error, isRefreshing } = usePollingQuery(
    () => api.analyticsSummary(lookbackHours, bucketHours),
    {
      intervalMs: refreshIntervalMs,
      reloadKey: analyticsEpoch,
      staleKey: paramKey,
      errorMessage: "Analytics betöltési hiba",
    },
  );

  const pnl = data?.pnl;
  const kpis = pnl?.kpis;
  const realized = useMemo(
    () => (kpis ? Number(kpis.realized_pnl_usdt) : 0),
    [kpis],
  );

  const chartKey = pnl
    ? `${pnl.lookback_hours}:${pnl.bucket_hours}:${pnl.buckets.length}:${pnl.window_end}`
    : "empty";

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
            Analytics
            <RefreshIndicator active={isRefreshing} />
          </h1>
          <p className="text-muted text-sm mt-1">
            Lezárt pozíciók realized PnL
            {pnl ? (
              <>
                {" "}
                · {lookbackLabel(pnl.lookback_hours)}, bucket {pnl.bucket_hours}h
                {pnl.window_start && pnl.window_end ? (
                  <>
                    {" "}
                    · {formatWindow(pnl.window_start)} – {formatWindow(pnl.window_end)}
                  </>
                ) : null}
                {pnl.positions_in_window != null
                  ? ` · ${pnl.positions_in_window} pozíció az ablakban`
                  : ""}
              </>
            ) : (
              ` · ${lookbackLabel(lookbackHours)}`
            )}
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
              onChange={(e) => setLookbackHours(Number(e.target.value) || 24)}
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

      {data && pnl && kpis && (
        <>
          <KpiRow pnl={pnl} realized={realized} />
          <Card>
            <CardHeader>
              <CardTitle>PnL idősor</CardTitle>
              {pnl.sync_error && (
                <span className="text-xs text-amber-400">{pnl.sync_error}</span>
              )}
            </CardHeader>
            <CardContent>
              <PnlSeriesChart key={chartKey} data={pnl} />
            </CardContent>
          </Card>
          {pnl.tp_sl_by_hour ? (
            <Card>
              <CardHeader>
                <CardTitle>TP / SL napszak szerint</CardTitle>
                <span className="text-xs text-muted">
                  Lezárt pozíciók száma óránként (0–23), napok összesítve ·{" "}
                  {lookbackLabel(pnl.lookback_hours)}
                </span>
              </CardHeader>
              <CardContent>
                <TpSlByHourChart data={pnl.tp_sl_by_hour} />
              </CardContent>
            </Card>
          ) : null}
          <AnalyticsBreakdown pnl={pnl} />
          <AnalyticsDbPanels orders={data.orders} strategy={data.strategy} />
        </>
      )}
    </div>
  );
}

function KpiRow({
  pnl,
  realized,
}: {
  pnl: PnlSeriesResponse;
  realized: number;
}) {
  const k = pnl.kpis;
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
      <StatCard
        label="Realized PnL"
        value={formatNumber(realized, { decimals: 4, sign: true })}
        unit="USDT"
        tone={toneOf(realized)}
        wrapValue
      />
      <StatCard
        label="Win rate"
        value={k.win_rate_pct ?? "—"}
        unit={k.win_rate_pct ? "%" : ""}
        wrapValue
      />
      <StatCard label="Pozíciók" value={String(k.count)} unit="db" />
      <StatCard
        label="Profit factor"
        value={k.profit_factor ?? "—"}
        hint="gross win / gross loss"
        wrapValue
      />
      <StatCard
        label="Expectancy"
        value={k.expectancy_usdt ?? "—"}
        unit="USDT / trade"
        wrapValue
      />
      <StatCard
        label="Max drawdown"
        value={formatNumber(k.max_drawdown_usdt, { decimals: 4 })}
        unit="USDT"
        tone="negative"
        wrapValue
      />
      <StatCard
        label="Átlag nyerő"
        value={k.avg_win_usdt ?? "—"}
        unit="USDT"
        tone="positive"
        wrapValue
      />
      <StatCard
        label="Átlag vesztes"
        value={k.avg_loss_usdt ?? "—"}
        unit="USDT"
        tone="negative"
        wrapValue
      />
    </div>
  );
}
