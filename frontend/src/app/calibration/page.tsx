"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  api,
  type CalibrationRun,
  type CalibrationSymbolRun,
} from "@/lib/api";
import { useRefreshInterval } from "@/contexts/RefreshIntervalContext";
import { useLiveEpoch } from "@/contexts/LiveUpdatesContext";

type Latest = Awaited<ReturnType<typeof api.calibrationLatest>>;

type QualifiedCandidate = {
  symbol: string;
  rank: number;
  abs_change_24h_pct: string;
  tp_roi_pct: string;
  sl_roi_pct: string;
  backtest_win_rate_pct: string;
  variation_label: string;
  trade_count: number;
  variations?: VariationRow[];
};

type VariationRow = {
  label: string;
  tp_roi_pct: string;
  sl_roi_pct: string;
  resolved_tp_win_rate_pct: string | null;
  meets_target: boolean;
  summary?: {
    total_trades: number;
    tp_wins: number;
    sl_losses: number;
    no_result: number;
  };
};

type CalibrationSummary = {
  mode?: string;
  candidates_target?: number;
  candidates_found?: number;
  scanned_symbols?: number;
  qualified_candidates?: QualifiedCandidate[];
  global?: {
    tp_move_pct?: string | null;
    sl_move_pct?: string | null;
    symbol_count?: number;
  };
  per_symbol?: Record<
    string,
    {
      tp_move_pct: string;
      sl_move_pct: string;
      tp_roi_pct?: string | null;
      sl_roi_pct?: string | null;
      backtest_win_rate_pct?: string | null;
      variation_label?: string | null;
      abs_change_24h_pct?: string;
      backtest_variations?: VariationRow[];
    }
  >;
};

export default function CalibrationPage() {
  const { refreshIntervalMs } = useRefreshInterval();
  const calEpoch = useLiveEpoch("calibration");
  const [latest, setLatest] = useState<Latest | null>(null);
  const [runs, setRuns] = useState<CalibrationRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);
  const [symbolRuns, setSymbolRuns] = useState<CalibrationSymbolRun[] | null>(
    null,
  );
  const [symbolRunsTotal, setSymbolRunsTotal] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const [l, r] = await Promise.all([
        api.calibrationLatest(),
        api.calibrationRuns(20),
      ]);
      setLatest(l);
      setRuns(r);
      const calId = l.symbol_runs_calibration_id ?? null;
      if (calId) {
        const sr = await api.calibrationSymbolRuns(calId, {
          order_by: "max_win_rate",
          limit: 500,
        });
        setSymbolRuns(sr.items);
        setSymbolRunsTotal(sr.total);
      } else {
        setSymbolRuns(null);
        setSymbolRunsTotal(0);
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ismeretlen hiba");
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = setInterval(refresh, refreshIntervalMs);
    return () => clearInterval(id);
  }, [refresh, refreshIntervalMs, calEpoch]);

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

  const tradingEnabled = latest?.trading_enabled ?? false;
  const isRunning = latest?.latest?.status === "RUNNING";
  const summary = (
    isRunning
      ? latest?.latest?.summary
      : latest?.latest_successful?.summary
  ) as CalibrationSummary | undefined;
  const qualified = isRunning ? [] : (summary?.qualified_candidates ?? []);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Jelölt-kalibráció (7 nap backtest)</CardTitle>
          <span className="text-xs text-muted">
            Top 500 mozgó · live belépés :15/:20/:25 · kalibráció :15 · ≥80% win
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
              label="Következő futás (:30)"
              value={
                latest?.next_run_after
                  ? new Date(latest.next_run_after).toLocaleString("hu-HU", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })
                  : "—"
              }
              tone="neutral"
            />
          </div>
          {isRunning && (
            <p className="text-sm text-muted mb-3">
              Futás folyamatban (kalibráció #{latest?.symbol_runs_calibration_id}
              ) — eddig{" "}
              <strong>{latest?.symbol_runs_persisted ?? 0}</strong> coin mentve
              DB-be.
            </p>
          )}
          {summary && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4 text-sm">
              <Metric
                label="Jelöltek"
                value={`${summary.candidates_found ?? 0} / ${summary.candidates_target ?? "?"}`}
              />
              <Metric
                label="Átvizsgált coin"
                value={String(
                  isRunning
                    ? (latest?.symbol_runs_persisted ?? summary.scanned_symbols ?? 0)
                    : (summary.scanned_symbols ?? 0),
                )}
              />
              <Metric
                label="Lookback"
                value={`${Math.round(
                  ((latest?.latest?.lookback_minutes ??
                    latest?.latest_successful?.lookback_minutes ??
                    0) as number) /
                    60 /
                    24,
                )} nap`}
              />
              <Metric label="Mód" value={summary.mode ?? "—"} />
            </div>
          )}
          <div className="flex items-center justify-between gap-4">
            <p className="text-sm text-muted">
              A scheduler minden óra <strong>:30</strong>-kor indul, ha van szabad
              pozícióslot. Csak a backtesten átment coinokra nyit a stratégia.
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

      {symbolRuns && symbolRuns.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>
              Összes coin backtest ({symbolRunsTotal} sor, DB)
            </CardTitle>
            <span className="text-xs text-muted">
              Legjobb variáció max win % szerint · részletek:{" "}
              <code className="text-xs">tpsl_calibration_symbol_runs</code>
            </span>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase text-muted border-b border-border">
                  <tr>
                    <th className="text-left py-2 pr-3">#</th>
                    <th className="text-left py-2 pr-3">Szimbólum</th>
                    <th className="text-right py-2 pr-3">Max win %</th>
                    <th className="text-right py-2 pr-3">Best win %</th>
                    <th className="text-left py-2 pr-3">Ok</th>
                    <th className="text-left py-2 pr-3">Variáció</th>
                    <th className="text-right py-2 pr-3">Trade</th>
                  </tr>
                </thead>
                <tbody>
                  {symbolRuns.map((row) => (
                    <tr
                      key={row.id}
                      className={`border-b border-border/50 ${
                        row.is_qualified ? "bg-profit/5" : ""
                      }`}
                    >
                      <td className="py-2 pr-3 num text-muted">
                        {row.scan_rank}
                      </td>
                      <td className="py-2 pr-3 font-medium">{row.symbol}</td>
                      <td className="py-2 pr-3 text-right num">
                        {row.max_win_rate_pct != null
                          ? `${row.max_win_rate_pct}%`
                          : "—"}
                      </td>
                      <td className="py-2 pr-3 text-right num">
                        {row.best_win_rate_pct != null
                          ? `${row.best_win_rate_pct}%`
                          : "—"}
                      </td>
                      <td className="py-2 pr-3 text-xs text-muted">
                        {row.reason}
                        {row.is_qualified ? " ✓" : ""}
                      </td>
                      <td className="py-2 pr-3 text-muted">
                        {row.best_variation_label ?? "—"}
                      </td>
                      <td className="py-2 pr-3 text-right num">
                        {row.best_total_trades ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {symbolRunsTotal > symbolRuns.length && (
              <p className="text-xs text-muted mt-2">
                Első {symbolRuns.length} / {symbolRunsTotal} sor (API limit).
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {qualified.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Minősített jelöltek (≥80% TP win)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase text-muted border-b border-border">
                  <tr>
                    <th className="text-left py-2 pr-3">#</th>
                    <th className="text-left py-2 pr-3">Szimbólum</th>
                    <th className="text-right py-2 pr-3">Win %</th>
                    <th className="text-right py-2 pr-3">TP ROI</th>
                    <th className="text-right py-2 pr-3">SL ROI</th>
                    <th className="text-left py-2 pr-3">Variáció</th>
                    <th className="text-right py-2 pr-3">|24h %|</th>
                    <th className="text-right py-2 pr-3">Trade</th>
                    <th className="text-left py-2 pr-3" />
                  </tr>
                </thead>
                <tbody>
                  {qualified.map((c) => (
                    <Fragment key={c.symbol}>
                      <tr
                        className="border-b border-border/50 cursor-pointer hover:bg-bg-subtle/50"
                        onClick={() =>
                          setExpandedSymbol(
                            expandedSymbol === c.symbol ? null : c.symbol,
                          )
                        }
                      >
                        <td className="py-2 pr-3 num text-muted">{c.rank}</td>
                        <td className="py-2 pr-3 font-medium">{c.symbol}</td>
                        <td className="py-2 pr-3 text-right num text-profit">
                          {c.backtest_win_rate_pct}%
                        </td>
                        <td className="py-2 pr-3 text-right num">{c.tp_roi_pct}%</td>
                        <td className="py-2 pr-3 text-right num">{c.sl_roi_pct}%</td>
                        <td className="py-2 pr-3 text-muted">{c.variation_label}</td>
                        <td className="py-2 pr-3 text-right num">
                          {c.abs_change_24h_pct}%
                        </td>
                        <td className="py-2 pr-3 text-right num">{c.trade_count}</td>
                        <td className="py-2 pr-3 text-xs text-muted">
                          {expandedSymbol === c.symbol ? "▲" : "▼"} variációk
                        </td>
                      </tr>
                      {expandedSymbol === c.symbol &&
                        (c.variations?.length ?? 0) > 0 && (
                          <tr className="bg-bg-subtle/30">
                            <td colSpan={9} className="py-2 px-2">
                              <VariationTable rows={c.variations ?? []} />
                            </td>
                          </tr>
                        )}
                    </Fragment>
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
                    <th className="text-right py-2 pr-3">Jelöltek</th>
                    <th className="text-right py-2 pr-3">Scan</th>
                    <th className="text-left py-2 pr-3">Összegzés</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => {
                    const s = r.summary as CalibrationSummary | undefined;
                    return (
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
                          {s?.candidates_found ?? "—"}/{s?.candidates_target ?? "—"}
                        </td>
                        <td className="py-2 pr-3 text-right num">
                          {s?.scanned_symbols ?? "—"}
                        </td>
                        <td className="py-2 pr-3 text-xs text-muted">
                          {r.error ? (
                            <span className="text-loss">{r.error}</span>
                          ) : (
                            <span>
                              {s?.qualified_candidates?.length ?? 0} minősített
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}


function VariationTable({ rows }: { rows: VariationRow[] }) {
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-muted">
          <th className="text-left py-1">Variáció</th>
          <th className="text-right py-1">Win %</th>
          <th className="text-right py-1">TP ROI</th>
          <th className="text-right py-1">SL ROI</th>
          <th className="text-right py-1">Trade</th>
          <th className="text-center py-1">≥80%</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((v) => (
          <tr key={v.label} className="border-t border-border/30">
            <td className="py-1">{v.label}</td>
            <td className="py-1 text-right num">
              {v.resolved_tp_win_rate_pct ?? "—"}%
            </td>
            <td className="py-1 text-right num">{v.tp_roi_pct}%</td>
            <td className="py-1 text-right num">{v.sl_roi_pct}%</td>
            <td className="py-1 text-right num">{v.summary?.total_trades ?? "—"}</td>
            <td className="py-1 text-center">
              {v.meets_target ? (
                <span className="text-profit">✓</span>
              ) : (
                <span className="text-muted">—</span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
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
