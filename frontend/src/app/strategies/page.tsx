"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { buildCsv, downloadCsvFile } from "@/lib/csvExport";
import {
  api,
  type SettingsSnapshot,
  type StrategyInfo,
  type StrategyRun,
} from "@/lib/api";
import { strategyPatchKey } from "@/lib/runtimeControls";
import { useRefreshInterval } from "@/contexts/RefreshIntervalContext";
import { useLiveEpoch } from "@/contexts/LiveUpdatesContext";
import { cn } from "@/lib/utils";
import { TopSignalEntriesConfigEditor } from "@/components/TopSignalEntriesConfigEditor";
import type { TopSignalEntriesConfig } from "@/lib/api";

const RUNS_LIMIT = 8;

export default function StrategiesPage() {
  const { refreshIntervalMs } = useRefreshInterval();
  const stratEpoch = useLiveEpoch("strategies");
  const settingsEpoch = useLiveEpoch("settings");
  const [list, setList] = useState<StrategyInfo[] | null>(null);
  const [runs, setRuns] = useState<StrategyRun[] | null>(null);
  const [snap, setSnap] = useState<SettingsSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [toggleBusy, setToggleBusy] = useState<string | null>(null);
  const [tseConfig, setTseConfig] = useState<TopSignalEntriesConfig | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [l, r, s, tse] = await Promise.all([
        api.strategies(),
        api.strategyRuns(undefined, RUNS_LIMIT),
        api.settingsSnapshot(),
        api.getTopSignalEntriesConfig(),
      ]);
      setList(l);
      setRuns(r);
      setSnap(s);
      setTseConfig(tse.config);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ismeretlen hiba");
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = setInterval(refresh, refreshIntervalMs);
    return () => clearInterval(id);
  }, [refresh, refreshIntervalMs, stratEpoch, settingsEpoch]);

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

  async function patchRuntime(
    key: "bitunix_live_trading" | "strategy_top_signal_entries_enabled",
    value: boolean,
  ) {
    setToggleBusy(key);
    try {
      await api.patchSettings({ [key]: value });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Mentés sikertelen");
    } finally {
      setToggleBusy(null);
    }
  }

  async function toggleStrategy(name: string, enabled: boolean) {
    const patchKey = strategyPatchKey(name);
    if (!patchKey) return;
    await patchRuntime(patchKey, enabled);
  }

  const liveTrading = snap?.effective.live_trading ?? false;
  const strategiesEff = snap?.effective.strategies ?? {};

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-slate-100">Stratégiák</h1>
        <p className="text-muted text-sm mt-1">
          Algoritmus paraméterek itt mentődnek (DB). Bekapcsolás és élő trading a{" "}
          <Link href="/settings" className="text-accent hover:underline">
            vezérlőpulton
          </Link>{" "}
          is állítható.
        </p>
      </header>

      {error && (
        <p className="text-loss text-sm border border-loss/40 rounded-md px-3 py-2">
          {error}
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Futtatás vezérlés</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              className="mt-1"
              checked={liveTrading}
              disabled={toggleBusy !== null}
              onChange={(e) => void patchRuntime("bitunix_live_trading", e.target.checked)}
            />
            <span>
              <span className="font-medium text-slate-200 block">
                Élő trading (Bitunix)
              </span>
              <span className="text-xs text-muted">
                {liveTrading
                  ? "Valódi rendelések engedélyezve."
                  : "Dry-run: nincs tőzsdei order."}
              </span>
            </span>
          </label>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>top_signal_entries paraméterek</CardTitle>
          <span className="text-xs text-muted">
            alapértelmezés kódban; mentés után DB-ben
          </span>
        </CardHeader>
        <CardContent>
          {!tseConfig && <p className="text-muted text-sm">Betöltés…</p>}
          {tseConfig && (
            <TopSignalEntriesConfigEditor
              initial={tseConfig}
              onSaved={() => void refresh()}
            />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Regisztrált stratégiák</CardTitle>
          <span className="text-xs text-muted">bekapcsolás runtime (DB)</span>
        </CardHeader>
        <CardContent>
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
                {list.map((s) => {
                  const patchKey = strategyPatchKey(s.name);
                  const effEnabled = strategiesEff[s.name] ?? s.enabled;
                  return (
                    <tr key={s.name} className="border-b border-border/50">
                      <td className="py-2 pr-3 font-medium">{s.name}</td>
                      <td className="py-2 pr-3">
                        {patchKey ? (
                          <label className="inline-flex items-center gap-2 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={effEnabled}
                              disabled={toggleBusy !== null}
                              onChange={(e) =>
                                void toggleStrategy(s.name, e.target.checked)
                              }
                            />
                            <span
                              className={cn(
                                "text-xs",
                                effEnabled ? "text-profit" : "text-muted",
                              )}
                            >
                              {effEnabled ? "bekapcsolva" : "kikapcsolva"}
                            </span>
                          </label>
                        ) : (
                          <span
                            className={
                              s.enabled ? "text-profit" : "text-muted"
                            }
                          >
                            {s.enabled ? "igen" : "kikapcsolva"}
                          </span>
                        )}
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
                          disabled={running === s.name || !effEnabled}
                          onClick={() => trigger(s.name)}
                        >
                          {running === s.name ? "Fut…" : "Indítás most"}
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle>Legutóbbi futások</CardTitle>
            <span className="text-xs text-muted">
              utolsó {RUNS_LIMIT} · részletek kinyitható
            </span>
          </div>
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
            <ul className="max-h-56 overflow-y-auto space-y-1 text-sm divide-y divide-border/40">
              {runs.map((r) => (
                <li key={r.id} className="py-1.5">
                  <details className="group">
                    <summary className="cursor-pointer list-none flex flex-wrap items-center gap-x-3 gap-y-1">
                      <span className="text-muted num text-xs">
                        {r.started_at
                          ? new Date(r.started_at).toLocaleString("hu-HU", {
                              month: "short",
                              day: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                          : "—"}
                      </span>
                      <span className="font-mono text-slate-200">{r.strategy_name}</span>
                      <StatusBadge status={r.status} />
                      <RunSummaryInline details={r.details} error={r.error} />
                      <span className="text-xs text-muted ml-auto group-open:hidden">
                        ▾
                      </span>
                    </summary>
                    <div className="mt-2 pl-2 border-l border-border/50">
                      <RunDetailsBody run={r} />
                    </div>
                  </details>
                </li>
              ))}
            </ul>
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
      className={`inline-block rounded px-1.5 py-0.5 text-[10px] border ${colorMap[status] ?? "bg-muted/20 text-muted border-muted/40"}`}
    >
      {status}
    </span>
  );
}

function RunSummaryInline({
  details,
  error,
}: {
  details: Record<string, unknown> | null;
  error: string | null;
}) {
  if (error) {
    return (
      <span className="text-loss text-xs truncate max-w-[12rem]">
        {error.slice(0, 80)}
        {error.length > 80 ? "…" : ""}
      </span>
    );
  }
  if (!details) return null;
  const placed = (details.placed_orders as unknown[] | undefined)?.length ?? 0;
  const skipped = (details.skipped as unknown[] | undefined)?.length ?? 0;
  return (
    <span className="text-xs text-muted">
      placed {placed} · skip {skipped}
    </span>
  );
}

function RunDetailsBody({ run }: { run: StrategyRun }) {
  if (run.error) {
    return (
      <pre className="whitespace-pre-wrap break-words text-loss text-xs leading-snug">
        {run.error}
      </pre>
    );
  }
  return <RunDetailsSummary details={run.details} />;
}

function RunDetailsSummary({ details }: { details: Record<string, unknown> | null }) {
  if (!details) return <span className="text-muted text-xs">—</span>;
  const placed = (details.placed_orders as unknown[] | undefined) || [];
  const skipped = (details.skipped as unknown[] | undefined) || [];
  return (
    <div className="text-xs space-y-0.5 text-muted">
      <div>
        <span className="text-profit">placed: {placed.length}</span>
        <span className="mx-2">·</span>
        <span>skipped: {skipped.length}</span>
      </div>
      {typeof details.margin_per_position_usdt === "string" && (
        <div>
          margin/poz:{" "}
          <span className="num text-slate-200">{details.margin_per_position_usdt}</span> USDT
        </div>
      )}
      {typeof details.reason === "string" && <div>ok: {details.reason}</div>}
    </div>
  );
}
