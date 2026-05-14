"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { buildCsv, downloadCsvFile } from "@/lib/csvExport";
import { api, type StrategyInfo, type StrategyRun } from "@/lib/api";
import { useRefreshInterval } from "@/contexts/RefreshIntervalContext";
import { useLiveEpoch, useLivePushConnected } from "@/contexts/LiveUpdatesContext";

export default function StrategiesPage() {
  const { refreshIntervalMs } = useRefreshInterval();
  const pushConnected = useLivePushConnected();
  const stratEpoch = useLiveEpoch("strategies");
  const [list, setList] = useState<StrategyInfo[] | null>(null);
  const [runs, setRuns] = useState<StrategyRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [l, r] = await Promise.all([api.strategies(), api.strategyRuns()]);
      setList(l);
      setRuns(r);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ismeretlen hiba");
    }
  }, []);

  useEffect(() => {
    void refresh();
    if (pushConnected) {
      return undefined;
    }
    const id = setInterval(refresh, refreshIntervalMs);
    return () => clearInterval(id);
  }, [refresh, refreshIntervalMs, pushConnected, stratEpoch]);

  const exportRunsCsv = useCallback(() => {
    if (!runs?.length) return;
    const headers = [
      "id",
      "started_at",
      "finished_at",
      "strategy_name",
      "triggered_by",
      "status",
      "error",
      "details_json",
    ];
    const dataRows = runs.map((r) => [
      String(r.id),
      r.started_at ?? "",
      r.finished_at ?? "",
      r.strategy_name,
      r.triggered_by,
      r.status ?? "",
      r.error ?? "",
      r.details ? JSON.stringify(r.details) : "",
    ]);
    downloadCsvFile(
      `strategy-runs-${new Date().toISOString().slice(0, 19).replace(/:/g, "-")}.csv`,
      buildCsv(headers, dataRows),
    );
  }, [runs]);

  async function trigger(name: string) {
    setRunning(name);
    try {
      await api.triggerStrategy(name);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Indítás sikertelen");
    } finally {
      setRunning(null);
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Regisztrált stratégiák</CardTitle>
          <span className="text-xs text-muted">scheduler állapota a backend ENV alapján</span>
        </CardHeader>
        <CardContent>
          {error && <p className="text-loss text-sm mb-2">{error}</p>}
          {!list && <p className="text-muted text-sm">Betöltés…</p>}
          {list && list.length === 0 && (
            <p className="text-muted text-sm">Nincs regisztrált stratégia.</p>
          )}
          {list && list.length > 0 && (
            <table className="w-full text-sm">
              <thead className="text-xs uppercase text-muted border-b border-border">
                <tr>
                  <th className="text-left py-2 pr-3">Név</th>
                  <th className="text-left py-2 pr-3">Bekapcsolva</th>
                  <th className="text-left py-2 pr-3">Utolsó futás</th>
                  <th className="text-left py-2 pr-3">Státusz</th>
                  <th className="text-right py-2">Akció</th>
                </tr>
              </thead>
              <tbody>
                {list.map((s) => (
                  <tr key={s.name} className="border-b border-border/50">
                    <td className="py-2 pr-3 font-medium">{s.name}</td>
                    <td className="py-2 pr-3">
                      <span
                        className={
                          s.enabled
                            ? "text-profit"
                            : "text-muted"
                        }
                      >
                        {s.enabled ? "igen" : "kikapcsolva"}
                      </span>
                    </td>
                    <td className="py-2 pr-3 text-muted num">
                      {s.last_run?.started_at
                        ? new Date(s.last_run.started_at).toLocaleString("hu-HU")
                        : "—"}
                    </td>
                    <td className="py-2 pr-3">
                      <StatusBadge status={s.last_run?.status ?? null} />
                    </td>
                    <td className="py-2 pr-3 text-right">
                      <Button
                        variant="secondary"
                        disabled={running === s.name}
                        onClick={() => trigger(s.name)}
                      >
                        {running === s.name ? "Fut…" : "Indítás most"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>Legutóbbi futások</CardTitle>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="shrink-0"
            disabled={!runs?.length}
            onClick={() => exportRunsCsv()}
          >
            CSV export
          </Button>
        </CardHeader>
        <CardContent>
          {!runs && <p className="text-muted text-sm">Betöltés…</p>}
          {runs && runs.length === 0 && (
            <p className="text-muted text-sm">Még nem futott egy stratégia sem.</p>
          )}
          {runs && runs.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase text-muted border-b border-border">
                  <tr>
                    <th className="text-left py-2 pr-3">Indítás</th>
                    <th className="text-left py-2 pr-3">Stratégia</th>
                    <th className="text-left py-2 pr-3">Forrás</th>
                    <th className="text-left py-2 pr-3">Státusz</th>
                    <th className="text-left py-2 pr-3">Részlet</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.id} className="border-b border-border/50 align-top">
                      <td className="py-2 pr-3 text-muted num">
                        {r.started_at
                          ? new Date(r.started_at).toLocaleString("hu-HU")
                          : "—"}
                      </td>
                      <td className="py-2 pr-3 font-medium">{r.strategy_name}</td>
                      <td className="py-2 pr-3 text-muted">{r.triggered_by}</td>
                      <td className="py-2 pr-3">
                        <StatusBadge status={r.status} />
                      </td>
                      <td className="py-2 pr-3 max-w-xl">
                        <RunResultCell run={r} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-muted">—</span>;
  const colorMap: Record<string, string> = {
    SUCCESS: "bg-profit/20 text-profit border-profit/40",
    NO_OP: "bg-muted/20 text-muted border-muted/40",
    FAILED: "bg-loss/20 text-loss border-loss/40",
    RUNNING: "bg-accent/20 text-accent border-accent/40",
  };
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-xs border ${colorMap[status] ?? "bg-muted/20 text-muted border-muted/40"}`}
    >
      {status}
    </span>
  );
}

function RunResultCell({ run }: { run: StrategyRun }) {
  if (run.error) {
    const failure =
      run.details &&
      typeof run.details === "object" &&
      run.details !== null &&
      "failure" in run.details
        ? (run.details as Record<string, unknown>).failure
        : null;
    return (
      <div className="space-y-2">
        <pre className="whitespace-pre-wrap break-words text-loss text-xs leading-snug">
          {run.error}
        </pre>
        {failure != null && (
          <details className="text-xs">
            <summary className="cursor-pointer text-muted hover:text-fg">
              Strukturált hiba (API / traceback)
            </summary>
            <pre className="mt-2 max-h-64 overflow-auto rounded-md border border-border bg-bg-subtle p-2 font-mono text-[11px] leading-snug">
              {JSON.stringify(failure, null, 2)}
            </pre>
          </details>
        )}
      </div>
    );
  }
  return <RunDetailsSummary details={run.details} />;
}

function RunDetailsSummary({ details }: { details: Record<string, unknown> | null }) {
  if (!details) return <span className="text-muted">—</span>;
  const placed = (details.placed_orders as unknown[] | undefined) || [];
  const skipped = (details.skipped as unknown[] | undefined) || [];
  return (
    <div className="text-xs space-y-0.5">
      <div>
        <span className="text-profit">placed: {placed.length}</span>
        <span className="mx-2 text-muted">·</span>
        <span className="text-muted">skipped: {skipped.length}</span>
      </div>
      {typeof details.margin_per_position_usdt === "string" && (
        <div className="text-muted">
          margin/poz: <span className="num">{details.margin_per_position_usdt}</span>{" "}
          USDT
        </div>
      )}
    </div>
  );
}
