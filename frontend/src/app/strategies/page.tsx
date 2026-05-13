"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type StrategyInfo, type StrategyRun } from "@/lib/api";

export default function StrategiesPage() {
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
    const id = setInterval(refresh, 7000);
    return () => clearInterval(id);
  }, [refresh]);

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
        <CardHeader>
          <CardTitle>Legutóbbi futások</CardTitle>
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
                      <td className="py-2 pr-3">
                        {r.error ? (
                          <span className="text-loss">{r.error}</span>
                        ) : (
                          <RunDetailsSummary details={r.details} />
                        )}
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
