"use client";

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
import type { TpSlByHourResponse } from "@/lib/api";
import { CHART_TOOLTIP_STYLE } from "@/lib/chartTheme";

export function TpSlByHourChart({ data }: { data: TpSlByHourResponse }) {
  const chartData = data.hours.map((h) => ({
    label: `${String(h.hour).padStart(2, "0")}:00`,
    tp: h.tp_count,
    sl: h.sl_count,
  }));

  const hasAny = data.total_tp > 0 || data.total_sl > 0;

  if (!hasAny) {
    return (
      <p className="text-muted text-sm py-6 text-center">
        Nincs lezárt pozíció TP/SL bontásban az ablakban.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted leading-relaxed">{data.classification_note}</p>
      <p className="text-xs text-muted">
        Összesen: <span className="text-profit num">{data.total_tp} TP</span>
        {" · "}
        <span className="text-loss num">{data.total_sl} SL</span>
        {" · "}
        időzóna: {data.timezone}
      </p>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 10 }}
              stroke="#94a3b8"
              interval={1}
            />
            <YAxis
              allowDecimals={false}
              tick={{ fontSize: 10 }}
              stroke="#94a3b8"
              width={28}
            />
            <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="tp" name="TP (nyereséges)" fill="#22c55e" radius={[2, 2, 0, 0]} />
            <Bar dataKey="sl" name="SL (vesztes)" fill="#ef4444" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
