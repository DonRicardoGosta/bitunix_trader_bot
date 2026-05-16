"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PnlSeriesResponse } from "@/lib/api";
import { CHART_TOOLTIP_STYLE } from "@/lib/chartTheme";
import { formatNumber } from "@/lib/utils";

function num(v: string | null | undefined): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function windowCaption(data: PnlSeriesResponse): string | null {
  if (!data.window_start || !data.window_end) return null;
  const fmt = (iso: string) =>
    new Date(iso).toLocaleString("hu-HU", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
    });
  const endLabel = data.window_end_live ? "most" : fmt(data.window_end);
  return `${fmt(data.window_start)} – ${endLabel}`;
}

function toChartRows(data: PnlSeriesResponse) {
  const bucketData = data.buckets.map((b) => ({
    label: new Date(b.bucket_start).toLocaleString("hu-HU", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
    }),
    pnl: num(b.realized_pnl_usdt),
  }));

  const cumData = data.cumulative.map((c) => ({
    label: new Date(c.at).toLocaleString("hu-HU", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
    }),
    cumulative: num(c.cumulative_pnl_usdt),
  }));

  return { bucketData, cumData };
}

export function PnlSeriesChart({
  data,
  freezeKey,
}: {
  data: PnlSeriesResponse;
  /** Ablak/bucket váltáskor újra mount (nem minden poll-nál). */
  freezeKey?: string;
}) {
  const [hoverPaused, setHoverPaused] = useState(false);
  const [displayData, setDisplayData] = useState(data);
  const latestRef = useRef(data);

  useEffect(() => {
    latestRef.current = data;
    if (!hoverPaused) {
      setDisplayData(data);
    }
  }, [data, hoverPaused]);

  const resume = () => {
    setHoverPaused(false);
    setDisplayData(latestRef.current);
  };

  const { bucketData, cumData } = useMemo(() => toChartRows(displayData), [displayData]);
  const caption = windowCaption(displayData);

  if (bucketData.length === 0 && cumData.length === 0) {
    return (
      <p className="text-muted text-sm py-8 text-center">
        Nincs lezárt pozíció adat az időszakban
        {displayData.sync_error ? ` (${displayData.sync_error})` : "."}
      </p>
    );
  }

  return (
    <div
      key={freezeKey}
      className="space-y-2"
      onMouseEnter={() => setHoverPaused(true)}
      onMouseLeave={resume}
      onFocusCapture={() => setHoverPaused(true)}
      onBlurCapture={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
          resume();
        }
      }}
    >
      {caption && (
        <p className="text-xs text-muted flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <span>
            Grafikon ablak: {caption}
            {displayData.positions_in_window != null
              ? ` · ${displayData.positions_in_window} lezárt pozíció`
              : ""}
          </span>
          {hoverPaused ? (
            <span className="text-accent/90 normal-case">· szünet (egér fölött)</span>
          ) : null}
        </p>
      )}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <div className="h-64">
          <h3 className="text-xs uppercase text-muted mb-2">Realized PnL / bucket</h3>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={bucketData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} stroke="#94a3b8" />
              <YAxis tick={{ fontSize: 10 }} stroke="#94a3b8" />
              <Tooltip
                {...CHART_TOOLTIP_STYLE}
                formatter={(v: number) => [
                  formatNumber(v, { decimals: 4, sign: true }),
                  "PnL",
                ]}
              />
              <Bar
                dataKey="pnl"
                fill="#38bdf8"
                radius={[2, 2, 0, 0]}
                isAnimationActive={!hoverPaused}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="h-64">
          <h3 className="text-xs uppercase text-muted mb-2">Kumulatív realized PnL</h3>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={cumData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} stroke="#94a3b8" />
              <YAxis tick={{ fontSize: 10 }} stroke="#94a3b8" />
              <Tooltip
                {...CHART_TOOLTIP_STYLE}
                formatter={(v: number) => [
                  formatNumber(v, { decimals: 4, sign: true }),
                  "Összesen",
                ]}
              />
              <Area
                type="monotone"
                dataKey="cumulative"
                stroke="#4ade80"
                fill="#4ade8033"
                isAnimationActive={!hoverPaused}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
