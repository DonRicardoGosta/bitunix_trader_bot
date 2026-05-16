"use client";

import { useMemo, useState } from "react";
import type { TradeHoldDurationStats } from "@/lib/api";
import { formatDurationSec } from "@/lib/formatDuration";
import { Select } from "@/components/ui/input";

type ViewMode = "weekdays" | "hours";

const VIEW_LABELS: Record<ViewMode, string> = {
  weekdays: "Napok szerint",
  hours: "Órák szerint (0–23)",
};

type SideRow = {
  wins: { count: number; avg_duration_sec: number | null };
  losses: { count: number; avg_duration_sec: number | null };
};

function SummaryCards({ summary }: { summary: SideRow }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <div className="rounded-md border border-border/50 bg-bg-subtle/20 px-4 py-3">
        <p className="text-xs uppercase text-muted mb-1">Nyertes trade átlag tartam</p>
        <p className="text-lg font-semibold text-profit num">
          {formatDurationSec(summary.wins.avg_duration_sec)}
        </p>
        <p className="text-xs text-muted mt-1">{summary.wins.count} db trade</p>
      </div>
      <div className="rounded-md border border-border/50 bg-bg-subtle/20 px-4 py-3">
        <p className="text-xs uppercase text-muted mb-1">Vesztes trade átlag tartam</p>
        <p className="text-lg font-semibold text-loss num">
          {formatDurationSec(summary.losses.avg_duration_sec)}
        </p>
        <p className="text-xs text-muted mt-1">{summary.losses.count} db trade</p>
      </div>
    </div>
  );
}

function DurationTable({
  caption,
  rows,
  labelHeader,
}: {
  caption: string;
  labelHeader: string;
  rows: { key: string; label: string } & SideRow[];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border border-border/60 rounded-md overflow-hidden">
        <caption className="text-left text-xs uppercase text-muted mb-2 px-1">
          {caption}
        </caption>
        <thead className="bg-bg-subtle/60 text-xs uppercase text-muted">
          <tr>
            <th className="text-left py-2 px-3 font-medium">{labelHeader}</th>
            <th className="text-right py-2 px-3 font-medium">Nyertes átlag</th>
            <th className="text-right py-2 px-3 font-medium">Vesztes átlag</th>
            <th className="text-right py-2 px-3 font-medium">Nyertes db</th>
            <th className="text-right py-2 px-3 font-medium">Vesztes db</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="border-t border-border/40">
              <td className="py-1.5 px-3 text-slate-200">{row.label}</td>
              <td className="py-1.5 px-3 text-right text-profit num">
                {formatDurationSec(row.wins.avg_duration_sec)}
              </td>
              <td className="py-1.5 px-3 text-right text-loss num">
                {formatDurationSec(row.losses.avg_duration_sec)}
              </td>
              <td className="py-1.5 px-3 text-right num text-muted">{row.wins.count}</td>
              <td className="py-1.5 px-3 text-right num text-muted">{row.losses.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TradeHoldDurationPanel({ data }: { data: TradeHoldDurationStats }) {
  const [viewMode, setViewMode] = useState<ViewMode>("weekdays");

  const hasAny =
    data.summary.wins.count > 0 ||
    data.summary.losses.count > 0;

  const tableRows = useMemo(() => {
    if (viewMode === "weekdays") {
      return data.by_weekday.map((d) => ({
        key: String(d.weekday),
        label: d.label,
        wins: d.wins,
        losses: d.losses,
      }));
    }
    return data.by_hour.map((h) => ({
      key: String(h.hour),
      label: `${String(h.hour).padStart(2, "0")}:00`,
      wins: h.wins,
      losses: h.losses,
    }));
  }, [data, viewMode]);

  if (!hasAny) {
    return (
      <p className="text-muted text-sm py-6 text-center">
        Nincs számolható trade tartam az ablakban
        {data.skipped_no_duration > 0
          ? ` (${data.skipped_no_duration} pozíció hiányos időbélyeggel)`
          : "."}
      </p>
    );
  }

  return (
    <div className="space-y-5">
      <p className="text-xs text-muted leading-relaxed">{data.classification_note}</p>
      {data.skipped_no_duration > 0 ? (
        <p className="text-xs text-amber-400/90">
          {data.skipped_no_duration} lezárt pozíció kimaradt (nincs nyitás/lezárás idő).
        </p>
      ) : null}
      <SummaryCards summary={data.summary} />
      <div>
        <label className="block text-xs uppercase text-muted mb-1" htmlFor="hold-view">
          Bontás
        </label>
        <Select
          id="hold-view"
          value={viewMode}
          onChange={(e) => setViewMode(e.target.value as ViewMode)}
          className="max-w-xs"
        >
          {(Object.keys(VIEW_LABELS) as ViewMode[]).map((mode) => (
            <option key={mode} value={mode}>
              {VIEW_LABELS[mode]}
            </option>
          ))}
        </Select>
      </div>
      <DurationTable
        caption={VIEW_LABELS[viewMode]}
        labelHeader={viewMode === "weekdays" ? "Nap" : "Óra"}
        rows={tableRows}
      />
    </div>
  );
}
