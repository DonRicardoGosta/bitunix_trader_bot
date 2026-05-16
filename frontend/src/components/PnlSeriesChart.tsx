"use client";

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
  return `${fmt(data.window_start)} – ${fmt(data.window_end)}`;
}

export function PnlSeriesChart({ data }: { data: PnlSeriesResponse }) {
  const caption = windowCaption(data);

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

  if (bucketData.length === 0 && cumData.length === 0) {
    return (
      <p className="text-muted text-sm py-8 text-center">
        Nincs lezárt pozíció adat az időszakban
        {data.sync_error ? ` (${data.sync_error})` : "."}
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {caption && (
        <p className="text-xs text-muted">
          Grafikon ablak: {caption}
          {data.positions_in_window != null
            ? ` · ${data.positions_in_window} lezárt pozíció`
            : ""}
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
            <Bar dataKey="pnl" fill="#38bdf8" radius={[2, 2, 0, 0]} />
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
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
    </div>
  );
}
