"use client";

import type { TpSlTimingStats } from "@/lib/api";
import { cn } from "@/lib/utils";

function CountCell({ value, tone }: { value: number; tone: "tp" | "sl" }) {
  if (value === 0) {
    return <span className="text-muted num">0</span>;
  }
  return (
    <span
      className={cn(
        "num font-medium",
        tone === "tp" ? "text-profit" : "text-loss",
      )}
    >
      {value}
    </span>
  );
}

function TimingTable({
  caption,
  headers,
  rows,
}: {
  caption: string;
  headers: [string, string, string];
  rows: { key: string; label: string; tp: number; sl: number }[];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border border-border/60 rounded-md overflow-hidden">
        <caption className="text-left text-xs uppercase text-muted mb-2 px-1">
          {caption}
        </caption>
        <thead className="bg-bg-subtle/60 text-xs uppercase text-muted">
          <tr>
            <th className="text-left py-2 px-3 font-medium">{headers[0]}</th>
            <th className="text-right py-2 px-3 font-medium">{headers[1]}</th>
            <th className="text-right py-2 px-3 font-medium">{headers[2]}</th>
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
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TpSlTimingTables({ data }: { data: TpSlTimingStats }) {
  const hasAny = data.total_tp > 0 || data.total_sl > 0;

  if (!hasAny) {
    return (
      <p className="text-muted text-sm py-6 text-center">
        Nincs lezárt pozíció TP/SL bontásban az ablakban.
      </p>
    );
  }

  const hourRows = data.by_hour.map((h) => ({
    key: String(h.hour),
    label: `${String(h.hour).padStart(2, "0")}:00`,
    tp: h.tp_count,
    sl: h.sl_count,
  }));

  const weekdayRows = data.by_weekday.map((d) => ({
    key: String(d.weekday),
    label: d.label,
    tp: d.tp_count,
    sl: d.sl_count,
  }));

  return (
    <div className="space-y-6">
      <p className="text-xs text-muted leading-relaxed">{data.classification_note}</p>
      <p className="text-xs text-muted">
        Összesen: <span className="text-profit num">{data.total_tp} TP</span>
        {" · "}
        <span className="text-loss num">{data.total_sl} SL</span>
        {" · "}
        időzóna: {data.timezone}
      </p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <TimingTable
          caption="Óra szerint (0–23)"
          headers={["Óra", "TP", "SL"]}
          rows={hourRows}
        />
        <TimingTable
          caption="Hét napja szerint"
          headers={["Nap", "TP", "SL"]}
          rows={weekdayRows}
        />
      </div>
    </div>
  );
}
