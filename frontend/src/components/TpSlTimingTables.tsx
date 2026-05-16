"use client";

import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TpSlByHourBucket, TpSlTimingStats } from "@/lib/api";
import { CHART_TOOLTIP_STYLE } from "@/lib/chartTheme";
import {
  STORAGE_KEYS,
  type TpSlTimingViewMode,
  isTpSlTimingViewMode,
  isWeekdayIndex,
} from "@/lib/lookback";
import { usePersistedState, usePersistedStringState } from "@/hooks/usePersistedState";
import { Select } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type TimingRow = {
  key: string;
  label: string;
  tp: number;
  sl: number;
  net: number;
};

const VIEW_MODE_LABELS: Record<TpSlTimingViewMode, string> = {
  hours: "Órák (minden nap)",
  weekdays: "Napok (órák nélkül)",
  weekday_hours: "Egy nap órái",
};

function netCount(tp: number, sl: number): number {
  return tp - sl;
}

function sumRows(rows: TimingRow[]): { tp: number; sl: number; net: number } {
  const tp = rows.reduce((a, r) => a + r.tp, 0);
  const sl = rows.reduce((a, r) => a + r.sl, 0);
  return { tp, sl, net: netCount(tp, sl) };
}

function hourBucketsToRows(buckets: TpSlByHourBucket[]): TimingRow[] {
  return buckets.map((h) => ({
    key: String(h.hour),
    label: `${String(h.hour).padStart(2, "0")}:00`,
    tp: h.tp_count,
    sl: h.sl_count,
    net: netCount(h.tp_count, h.sl_count),
  }));
}

function CountCell({ value, tone }: { value: number; tone: "tp" | "sl" | "net" }) {
  if (value === 0) {
    return <span className="text-muted num">0</span>;
  }
  const cls =
    tone === "tp"
      ? "text-profit"
      : tone === "sl"
        ? "text-loss"
        : value > 0
          ? "text-profit"
          : "text-loss";
  const prefix = tone === "net" && value > 0 ? "+" : "";
  return (
    <span className={cn("num font-medium", cls)}>
      {prefix}
      {value}
    </span>
  );
}

function ViewSummary({ tp, sl, net }: { tp: number; sl: number; net: number }) {
  return (
    <p className="text-sm text-slate-200">
      <span className="text-profit num">{tp} TP</span>
      {" · "}
      <span className="text-loss num">{sl} SL</span>
      {" · "}
      <span className="text-muted">eredmény:</span>{" "}
      <CountCell value={net} tone="net" />
    </p>
  );
}

function TimingDataTable({ caption, rows }: { caption: string; rows: TimingRow[] }) {
  const footer = sumRows(rows);
  return (
    <TimingTableInner caption={caption} rows={rows} footer={footer} />
  );
}

function TimingTableInner({
  caption,
  rows,
  footer,
}: {
  caption: string;
  rows: TimingRow[];
  footer: { tp: number; sl: number; net: number };
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border border-border/60 rounded-md overflow-hidden">
        <caption className="text-left text-xs uppercase text-muted mb-2 px-1">
          {caption}
        </caption>
        <thead className="bg-bg-subtle/60 text-xs uppercase text-muted">
          <tr>
            <th className="text-left py-2 px-3 font-medium">Idő</th>
            <th className="text-right py-2 px-3 font-medium">TP</th>
            <th className="text-right py-2 px-3 font-medium">SL</th>
            <th className="text-right py-2 px-3 font-medium">Eredmény</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="border-t border-border/40">
              <td className="py-1.5 px-3 text-slate-200">{row.label}</td>
              <td className="py-1.5 px-3 text-right">
                <CountCell value={row.tp} tone="tp" />
              </td>
              <td className="py-1.5 px-3 text-right">
                <CountCell value={row.sl} tone="sl" />
              </td>
              <td className="py-1.5 px-3 text-right">
                <CountCell value={row.net} tone="net" />
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot className="border-t border-border/60 bg-bg-subtle/40 text-sm font-medium">
          <tr>
            <td className="py-2 px-3 text-slate-200">Összesen</td>
            <td className="py-2 px-3 text-right">
              <CountCell value={footer.tp} tone="tp" />
            </td>
            <td className="py-2 px-3 text-right">
              <CountCell value={footer.sl} tone="sl" />
            </td>
            <td className="py-2 px-3 text-right">
              <CountCell value={footer.net} tone="net" />
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function TpSlBarChart({ rows }: { rows: TimingRow[] }) {
  const chartData = rows.map((r) => ({
    label: r.label,
    tp: r.tp,
    sl: r.sl,
    net: r.net,
  }));
  const hasData = chartData.some((d) => d.tp > 0 || d.sl > 0);
  if (!hasData) {
    return <p className="text-muted text-sm py-4">Nincs megjeleníthető adat ebben a nézetben.</p>;
  }

  const tickInterval = rows.length > 12 ? Math.floor(rows.length / 12) : 0;

  return (
    <div className="h-56">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 48 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 10 }}
            stroke="#94a3b8"
            interval={tickInterval}
            angle={rows.length > 8 ? -45 : 0}
            textAnchor={rows.length > 8 ? "end" : "middle"}
            height={rows.length > 8 ? 56 : 32}
          />
          <YAxis allowDecimals={false} tick={{ fontSize: 10 }} stroke="#94a3b8" width={28} />
          <Tooltip
            {...CHART_TOOLTIP_STYLE}
            formatter={(value: number, name: string) => {
              if (name === "TP") return [value, "TP"];
              if (name === "SL") return [value, "SL"];
              return [value, name];
            }}
            labelFormatter={(label, payload) => {
              const item = payload?.[0]?.payload as { net?: number } | undefined;
              if (item?.net == null) return String(label);
              const sign = item.net > 0 ? "+" : "";
              return `${label} · eredmény ${sign}${item.net}`;
            }}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Bar dataKey="tp" name="TP" fill="#4ade80" radius={[2, 2, 0, 0]} />
          <Bar dataKey="sl" name="SL" fill="#f87171" radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function resolveViewRows(
  data: TpSlTimingStats,
  viewMode: TpSlTimingViewMode,
  weekday: number,
): { rows: TimingRow[]; caption: string } {
  if (viewMode === "hours") {
    return {
      rows: hourBucketsToRows(data.by_hour),
      caption: "Óra szerint (0–23), minden nap összesen",
    };
  }
  if (viewMode === "weekdays") {
    return {
      rows: data.by_weekday.map((d) => ({
        key: String(d.weekday),
        label: d.label,
        tp: d.tp_count,
        sl: d.sl_count,
        net: netCount(d.tp_count, d.sl_count),
      })),
      caption: "Hét napja szerint (órák nélkül)",
    };
  }
  const blocks = data.by_weekday_hour ?? [];
  const block = blocks.find((b) => b.weekday === weekday) ?? blocks[weekday];
  const label = block?.label ?? data.by_weekday[weekday]?.label ?? "—";
  const hours =
    block?.by_hour ??
    Array.from({ length: 24 }, (_, hour) => ({ hour, tp_count: 0, sl_count: 0 }));
  return {
    rows: hourBucketsToRows(hours),
    caption: `${label} órái (minden ${label} összesítve)`,
  };
}

export function TpSlTimingTables({ data }: { data: TpSlTimingStats }) {
  const hasAny = data.total_tp > 0 || data.total_sl > 0;
  const [viewMode, setViewMode] = usePersistedStringState(
    STORAGE_KEYS.analyticsTpSlViewMode,
    "hours",
    isTpSlTimingViewMode,
  );
  const [weekday, setWeekday] = usePersistedState(
    STORAGE_KEYS.analyticsTpSlWeekday,
    0,
    isWeekdayIndex,
  );

  const { rows, caption } = useMemo(
    () => resolveViewRows(data, viewMode, weekday),
    [data, viewMode, weekday],
  );
  const viewTotals = useMemo(() => sumRows(rows), [rows]);
  const globalNet = netCount(data.total_tp, data.total_sl);

  if (!hasAny) {
    return (
      <p className="text-muted text-sm py-6 text-center">
        Nincs lezárt pozíció TP/SL bontásban az ablakban.
      </p>
    );
  }

  const weekdayOptions =
    (data.by_weekday_hour?.length ?? 0) > 0 ? data.by_weekday_hour : data.by_weekday;

  return (
    <div className="space-y-5">
      <p className="text-xs text-muted leading-relaxed">{data.classification_note}</p>
      <p className="text-xs text-muted">
        Teljes ablak: <span className="text-profit num">{data.total_tp} TP</span>
        {" · "}
        <span className="text-loss num">{data.total_sl} SL</span>
        {" · "}
        eredmény <CountCell value={globalNet} tone="net" />
        {" · "}
        időzóna: {data.timezone}
      </p>

      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-xs uppercase text-muted mb-1" htmlFor="tpsl-view">
            Nézet
          </label>
          <Select
            id="tpsl-view"
            value={viewMode}
            onChange={(e) => {
              const v = e.target.value;
              if (isTpSlTimingViewMode(v)) setViewMode(v);
            }}
          >
            {(Object.keys(VIEW_MODE_LABELS) as TpSlTimingViewMode[]).map((mode) => (
              <option key={mode} value={mode}>
                {VIEW_MODE_LABELS[mode]}
              </option>
            ))}
          </Select>
        </div>
        {viewMode === "weekday_hours" ? (
          <div>
            <label className="block text-xs uppercase text-muted mb-1" htmlFor="tpsl-wd">
              Hét napja
            </label>
            <Select
              id="tpsl-wd"
              value={String(weekday)}
              onChange={(e) => setWeekday(Number(e.target.value) || 0)}
            >
              {weekdayOptions.map((d) => (
                <option key={d.weekday} value={String(d.weekday)}>
                  {d.label}
                </option>
              ))}
            </Select>
          </div>
        ) : null}
      </div>

      <div className="rounded-md border border-border/50 bg-bg-subtle/20 px-4 py-3">
        <p className="text-xs uppercase text-muted mb-1">Aktuális nézet</p>
        <ViewSummary tp={viewTotals.tp} sl={viewTotals.sl} net={viewTotals.net} />
        <p className="text-xs text-muted mt-1">{caption}</p>
      </div>

      <TpSlBarChart rows={rows} />

      <TimingDataTable caption={caption} rows={rows} />
    </div>
  );
}
