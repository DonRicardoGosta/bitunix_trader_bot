"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type CalibrationRun } from "@/lib/api";
import { useRefreshInterval } from "@/contexts/RefreshIntervalContext";

type Latest = Awaited<ReturnType<typeof api.calibrationLatest>>;

export default function CalibrationPage() {
  const { refreshIntervalMs } = useRefreshInterval();
  const [latest, setLatest] = useState<Latest | null>(null);
  const [runs, setRuns] = useState<CalibrationRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [l, r] = await Promise.all([
        api.calibrationLatest(),
        api.calibrationRuns(20),
      ]);
      setLatest(l);
      setRuns(r);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ismeretlen hiba");
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = setInterval(refresh, refreshIntervalMs);
    return () => clearInterval(id);
  }, [refresh, refreshIntervalMs]);

  async function trigger() {
    setBusy(true);
    try {
      await api.triggerCalibration();
      setTimeout(refresh, 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Indítás sikertelen");
    } finally {
      setBusy(false);
    }
  }

  const status = latest?.latest_successful?.status ?? null;
  const tradingEnabled = latest?.trading_enabled ?? false;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>TP/SL Kalibráció</CardTitle>
          <span className="text-xs text-muted">
            top {latest?.latest?.top_n ?? "?"} coin, lookback {" "}
            {latest?.latest?.lookback_minutes ?? "?"} perc
          </span>
        </CardHeader>
        <CardContent>
          {error && <p className="text-loss text-sm mb-3">{error}</p>}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
            <Status
              label="Tradelés"
              value={tradingEnabled ? "engedélyezve" : "BLOKKOLVA"}
              tone={tradingEnabled ? "ok" : "bad"}
            />
            <Status
              label="Utolsó sikeres"
              value={
                latest?.latest_successful?.finished_at
                  ? new Date(
                      latest.latest_successful.finished_at,
                    ).toLocaleString("hu-HU")
                  : "nincs"
              }
              tone={latest?.latest_successful ? "ok" : "bad"}
            />
            <Status
              label="Aktuális státusz"
              value={status ?? "—"}
              tone={
                status === "SUCCESS" ? "ok" : status === "FAILED" ? "bad" : "neutral"
              }
            />
          </div>

          <div className="flex items-center justify-between">
            <p className="text-sm text-muted">
              A kalibrációs scheduler az app indulásakor egyszer, majd óránként
              fut. A trading csak akkor engedélyezett, ha legalább egy friss
              SIKERES kalibráció van.
            </p>
            <Button
              variant="primary"
              disabled={busy}
              onClick={trigger}
              className="shrink-0"
            >
              {busy ? "Indul…" : "Kalibrálás most"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {latest?.latest_successful?.summary?.global && (
        <Card>
          <CardHeader>
            <CardTitle>Globális TP/SL célok (medián)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
              <Metric
                label="TP move %"
                value={latest.latest_successful.summary.global.tp_move_pct ?? "—"}
              />
              <Metric
                label="SL move %"
                value={latest.latest_successful.summary.global.sl_move_pct ?? "—"}
              />
              <Metric
                label="Kalibrált coin"
                value={String(
                  latest.latest_successful.summary.global.symbol_count ?? 0,
                )}
              />
              <Metric
                label="R:R"
                value={(() => {
                  const tp = parseFloat(
                    latest.latest_successful.summary.global.tp_move_pct ?? "0",
                  );
                  const sl = parseFloat(
                    latest.latest_successful.summary.global.sl_move_pct ?? "0",
                  );
                  if (!sl) return "—";
                  return `${(tp / sl).toFixed(2)}:1`;
                })()}
              />
            </div>
          </CardContent>
        </Card>
      )}

      {latest?.latest_successful?.summary?.per_symbol &&
        Object.keys(latest.latest_successful.summary.per_symbol).length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Per-szimbólum kalibráció</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-xs uppercase text-muted border-b border-border">
                    <tr>
                      <th className="text-left py-2 pr-3">Szimbólum</th>
                      <th className="text-right py-2 pr-3">ATR %</th>
                      <th className="text-right py-2 pr-3">TP move %</th>
                      <th className="text-right py-2 pr-3">SL move %</th>
                      <th className="text-right py-2 pr-3">|24h %|</th>
                      <th className="text-right py-2 pr-3">Mintaszám</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(
                      latest.latest_successful.summary.per_symbol,
                    ).map(([sym, s]) => (
                      <tr key={sym} className="border-b border-border/50">
                        <td className="py-2 pr-3 font-medium">{sym}</td>
                        <td className="py-2 pr-3 text-right num">{s.atr_pct}</td>
                        <td className="py-2 pr-3 text-right num text-profit">
                          {s.tp_move_pct}
                        </td>
                        <td className="py-2 pr-3 text-right num text-loss">
                          {s.sl_move_pct}
                        </td>
                        <td className="py-2 pr-3 text-right num text-muted">
                          {s.abs_change_24h_pct}
                        </td>
                        <td className="py-2 pr-3 text-right num text-muted">
                          {s.samples}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )}

      <Card>
        <CardHeader>
          <CardTitle>Futás történet</CardTitle>
        </CardHeader>
        <CardContent>
          {!runs && <p className="text-muted text-sm">Betöltés…</p>}
          {runs && runs.length === 0 && (
            <p className="text-muted text-sm">Még nem futott kalibráció.</p>
          )}
          {runs && runs.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase text-muted border-b border-border">
                  <tr>
                    <th className="text-left py-2 pr-3">Indítás</th>
                    <th className="text-left py-2 pr-3">Státusz</th>
                    <th className="text-left py-2 pr-3">Forrás</th>
                    <th className="text-right py-2 pr-3">Lookback</th>
                    <th className="text-right py-2 pr-3">Top N</th>
                    <th className="text-left py-2 pr-3">Hiba / összegzés</th>
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
                      <td className="py-2 pr-3">
                        <StatusBadge status={r.status} />
                      </td>
                      <td className="py-2 pr-3 text-muted">{r.triggered_by}</td>
                      <td className="py-2 pr-3 text-right num">
                        {r.lookback_minutes}m
                      </td>
                      <td className="py-2 pr-3 text-right num">{r.top_n}</td>
                      <td className="py-2 pr-3 text-xs">
                        {r.error ? (
                          <span className="text-loss">{r.error}</span>
                        ) : (
                          <span className="text-muted">
                            {r.summary?.global?.symbol_count ?? 0} symbol,{" "}
                            tp {r.summary?.global?.tp_move_pct ?? "—"}% / sl{" "}
                            {r.summary?.global?.sl_move_pct ?? "—"}%
                          </span>
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

function Status({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "ok" | "bad" | "neutral";
}) {
  const color =
    tone === "ok" ? "text-profit" : tone === "bad" ? "text-loss" : "text-muted";
  return (
    <div className="rounded-md border border-border bg-bg-subtle p-3">
      <div className="text-xs uppercase text-muted">{label}</div>
      <div className={`text-base font-semibold mt-1 ${color}`}>{value}</div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase text-muted">{label}</div>
      <div className="num text-lg text-slate-50">{value}</div>
    </div>
  );
}

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-muted">—</span>;
  const colorMap: Record<string, string> = {
    SUCCESS: "bg-profit/20 text-profit border-profit/40",
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
