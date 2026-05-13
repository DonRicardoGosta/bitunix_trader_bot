"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { StatCard } from "@/components/ui/StatCard";
import {
  api,
  type DashboardSummary,
  type NormalizedPosition,
} from "@/lib/api";
import { cn, formatNumber } from "@/lib/utils";

function num(v: string | null | undefined): number | null {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function toneOf(n: number | null): "positive" | "negative" | "neutral" {
  if (n == null) return "neutral";
  if (n > 0) return "positive";
  if (n < 0) return "negative";
  return "neutral";
}

function pnlClass(n: number | null): string {
  if (n == null) return "";
  if (n > 0) return "text-profit";
  if (n < 0) return "text-loss";
  return "";
}

const LEVEL_COLOR: Record<string, string> = {
  DEBUG: "text-muted border-muted/40",
  INFO: "text-accent border-accent/40",
  WARNING: "text-yellow-400 border-yellow-400/40",
  ERROR: "text-loss border-loss/40",
};

export function DashboardOverview() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lookback, setLookback] = useState(7);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const r = await api.dashboardSummary(lookback);
        if (!cancelled) {
          setData(r);
          setError(null);
        }
      } catch (err) {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Hiba a dashboard lekérésekor");
      }
    }
    void load();
    const id = setInterval(load, 10000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [lookback]);

  const account = data?.exchange?.account ?? null;
  const open = data?.exchange?.open_positions;
  const closed = data?.exchange?.closed_positions;

  const equity = useMemo(() => {
    if (!account) return null;
    const avail = num(account.available) ?? 0;
    const margin = num(account.margin) ?? 0;
    const upnl = num(account.cross_unrealized_pnl) ?? 0;
    const upnl2 = num(account.isolation_unrealized_pnl) ?? 0;
    return avail + margin + upnl + upnl2;
  }, [account]);

  if (error) return <p className="text-loss text-sm">{error}</p>;
  if (!data) return <p className="text-muted text-sm">Betöltés…</p>;

  const realized = num(closed?.realized_pnl_usdt ?? null) ?? 0;
  const unrealized = num(open?.total_unrealized_pnl_usdt ?? null) ?? 0;
  const usedMargin = num(open?.total_margin_usdt ?? null) ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Áttekintés</h1>
          <p className="text-muted text-sm mt-1">
            Élő számla- és tradinginformáció · frissül 10mp-enként ·{" "}
            <span className="text-xs">
              utolsó frissítés:{" "}
              {new Date(data.generated_at).toLocaleString("hu-HU")}
            </span>
          </p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="block text-xs uppercase text-muted mb-1" htmlFor="dash-lookback">
              Visszatekintés
            </label>
            <Select
              id="dash-lookback"
              value={lookback}
              onChange={(e) => setLookback(Number(e.target.value) || 7)}
            >
              <option value={1}>1 nap</option>
              <option value={7}>7 nap</option>
              <option value={14}>14 nap</option>
              <option value={30}>30 nap</option>
              <option value={90}>90 nap</option>
            </Select>
          </div>
        </div>
      </div>

      {data.exchange.sync_error ? (
        <p className="text-xs text-amber-400 border border-amber-500/30 rounded-md px-3 py-2 bg-amber-500/5">
          Bitunix szinkron: {data.exchange.sync_error}
        </p>
      ) : null}

      {/* Számlaegyenleg KPI sor */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          label="Számlaegyenleg (equity)"
          value={equity != null ? formatNumber(equity, { decimals: 4 }) : "—"}
          unit={account?.margin_coin ?? "USDT"}
          tone="accent"
          hint={
            account?.available
              ? `elérhető: ${formatNumber(account.available, { decimals: 2 })}`
              : "—"
          }
        />
        <StatCard
          label="Foglalt margin"
          value={formatNumber(usedMargin, { decimals: 4 })}
          unit="USDT"
          hint={
            open?.count
              ? `${open.count} nyitott pozíción`
              : "nincs nyitott pozíció"
          }
        />
        <StatCard
          label="Nyitott PnL"
          value={formatNumber(unrealized, { decimals: 4, sign: true })}
          unit="USDT"
          tone={toneOf(unrealized)}
          hint={
            usedMargin > 0
              ? `${formatNumber((unrealized / usedMargin) * 100, { decimals: 2, sign: true })}% a marginen`
              : undefined
          }
        />
        <StatCard
          label={`Realizált (${closed?.lookback_days ?? lookback} nap)`}
          value={formatNumber(realized, { decimals: 4, sign: true })}
          unit="USDT"
          tone={toneOf(realized)}
          hint={
            closed && closed.count > 0
              ? `${closed.wins}/${closed.count} nyertes (${closed.win_rate_pct ?? "—"}%)`
              : "nincs adat"
          }
        />
      </div>

      {/* Trading szignál sor */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <ClosedStatsCard data={data} />
        <OrdersStatsCard data={data} />
        <StrategyCard data={data} />
      </div>

      {/* Top winners / losers / nyitott pozíciók */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <TopPositionsCard
          title="Top winners (zárt)"
          rows={closed?.top_winners ?? []}
          emptyText="Nincs nyertes pozíció a megadott időszakban."
        />
        <TopPositionsCard
          title="Top losers (zárt)"
          rows={closed?.top_losers ?? []}
          emptyText="Nincs vesztes pozíció a megadott időszakban."
        />
        <OpenPositionsMini
          rows={open?.items ?? []}
          empty="Nincs nyitott pozíció."
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PerSymbolCard rows={closed?.per_symbol ?? []} />
        <RecentEventsCard data={data} />
      </div>
    </div>
  );
}

function ClosedStatsCard({ data }: { data: DashboardSummary }) {
  const c = data.exchange.closed_positions;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Lezárt pozíció statisztika</CardTitle>
        <span className="text-xs text-muted">{c.lookback_days} napos ablak</span>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <Row label="Pozíciók száma" value={c.count.toString()} />
        <Row
          label="Nyertes / vesztes"
          value={`${c.wins} / ${c.losses}`}
        />
        <Row label="Win rate" value={c.win_rate_pct ? `${c.win_rate_pct}%` : "—"} />
        <Row
          label="Átlag nyereség"
          value={
            c.avg_win_usdt
              ? `${formatNumber(c.avg_win_usdt, { decimals: 4, sign: true })} USDT`
              : "—"
          }
          tone="positive"
        />
        <Row
          label="Átlag veszteség"
          value={
            c.avg_loss_usdt
              ? `${formatNumber(c.avg_loss_usdt, { decimals: 4, sign: true })} USDT`
              : "—"
          }
          tone="negative"
        />
      </CardContent>
    </Card>
  );
}

function OrdersStatsCard({ data }: { data: DashboardSummary }) {
  const o = data.orders;
  const statusEntries = Object.entries(o.by_status);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Rendelések (saját napló)</CardTitle>
        <span className="text-xs text-muted">DB audit alapján</span>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <Row label="Összesen" value={o.total.toString()} />
        <Row label="Utolsó 24 óra" value={o.last_24h.toString()} />
        <div>
          <div className="text-xs uppercase text-muted">Státusz szerint</div>
          <div className="flex flex-wrap gap-1.5 mt-1">
            {statusEntries.length === 0 ? (
              <span className="text-muted text-xs">—</span>
            ) : (
              statusEntries.map(([k, v]) => (
                <span
                  key={k}
                  className="rounded border border-border bg-bg-subtle px-2 py-0.5 text-xs"
                >
                  {k}: <span className="num">{v}</span>
                </span>
              ))
            )}
          </div>
        </div>
        <div>
          <div className="text-xs uppercase text-muted">Top szimbólumok (30 nap)</div>
          <div className="text-xs mt-1 space-y-0.5">
            {o.top_symbols_30d.slice(0, 5).map((s) => (
              <div key={s.symbol} className="flex justify-between gap-2">
                <span className="font-medium text-slate-200">{s.symbol}</span>
                <span className="num text-muted">{s.count}</span>
              </div>
            ))}
            {o.top_symbols_30d.length === 0 && (
              <p className="text-muted">Nincs adat.</p>
            )}
          </div>
        </div>
        <Link
          href="/orders"
          className="inline-block text-xs text-accent hover:underline"
        >
          Megnyitás →
        </Link>
      </CardContent>
    </Card>
  );
}

function StrategyCard({ data }: { data: DashboardSummary }) {
  const s = data.strategy;
  const successes = s.by_status_24h.SUCCESS ?? 0;
  const failures = s.by_status_24h.FAILED ?? 0;
  const noop = s.by_status_24h.NO_OP ?? 0;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Stratégia heartbeat</CardTitle>
        <span className="text-xs text-muted">utolsó 24 óra</span>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <Row label="Sikeres futás" value={successes.toString()} tone="positive" />
        <Row label="Sikertelen" value={failures.toString()} tone={failures > 0 ? "negative" : "neutral"} />
        <Row label="No-op" value={noop.toString()} />
        {s.last_success ? (
          <div className="text-xs text-muted">
            Utolsó sikeres:{" "}
            <span className="text-slate-200 font-medium">
              {s.last_success.strategy_name}
            </span>{" "}
            ·{" "}
            {s.last_success.started_at
              ? new Date(s.last_success.started_at).toLocaleString("hu-HU")
              : "—"}
          </div>
        ) : null}
        {s.last_failure ? (
          <div className="text-xs text-loss">
            Utolsó hiba:{" "}
            <span className="font-medium">{s.last_failure.strategy_name}</span> ·{" "}
            {s.last_failure.started_at
              ? new Date(s.last_failure.started_at).toLocaleString("hu-HU")
              : "—"}
          </div>
        ) : null}
        {s.last_calibration ? (
          <div className="text-xs text-muted">
            Utolsó kalibráció: {s.last_calibration.status} ·{" "}
            {s.last_calibration.finished_at
              ? new Date(s.last_calibration.finished_at).toLocaleString("hu-HU")
              : "—"}
          </div>
        ) : null}
        <Link href="/strategies" className="inline-block text-xs text-accent hover:underline">
          Stratégia oldal →
        </Link>
      </CardContent>
    </Card>
  );
}

function TopPositionsCard({
  title,
  rows,
  emptyText,
}: {
  title: string;
  rows: NormalizedPosition[];
  emptyText: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-muted text-sm">{emptyText}</p>
        ) : (
          <ul className="space-y-1.5 text-sm">
            {rows.map((p, i) => {
              const r = num(p.realized_pnl);
              const roi = num(p.roi_pct);
              return (
                <li
                  key={`${p.position_id ?? p.symbol}-${i}`}
                  className="flex items-center justify-between gap-3"
                >
                  <span className="font-medium text-slate-200">
                    {p.symbol ?? "—"}
                  </span>
                  <span className="flex items-baseline gap-3 tabular-nums">
                    <span className={cn("num", pnlClass(r))}>
                      {r == null
                        ? "—"
                        : formatNumber(r, { decimals: 4, sign: true })}
                    </span>
                    <span className={cn("text-xs", pnlClass(roi))}>
                      {roi == null ? "" : `${roi.toFixed(2)}%`}
                    </span>
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function OpenPositionsMini({
  rows,
  empty,
}: {
  rows: NormalizedPosition[];
  empty: string;
}) {
  const sorted = [...rows].sort((a, b) => {
    const av = num(a.unrealized_pnl) ?? 0;
    const bv = num(b.unrealized_pnl) ?? 0;
    return bv - av;
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Nyitott pozíciók</CardTitle>
        <Link
          href="/positions"
          className="text-xs text-accent hover:underline"
        >
          Részletek →
        </Link>
      </CardHeader>
      <CardContent>
        {sorted.length === 0 ? (
          <p className="text-muted text-sm">{empty}</p>
        ) : (
          <ul className="space-y-1.5 text-sm">
            {sorted.slice(0, 6).map((p, i) => {
              const u = num(p.unrealized_pnl);
              const roi = num(p.roi_pct);
              return (
                <li
                  key={`${p.position_id ?? p.symbol}-${i}`}
                  className="flex items-center justify-between gap-3"
                >
                  <span className="flex items-baseline gap-2 min-w-0">
                    <span className="font-medium text-slate-200 truncate">
                      {p.symbol ?? "—"}
                    </span>
                    <span
                      className={cn(
                        "text-[10px] uppercase rounded px-1.5 py-0.5 border",
                        p.side === "BUY"
                          ? "text-profit border-profit/40 bg-profit/10"
                          : "text-loss border-loss/40 bg-loss/10",
                      )}
                    >
                      {p.side ?? "?"} {p.leverage != null ? `${p.leverage}x` : ""}
                    </span>
                  </span>
                  <span className="flex items-baseline gap-3 tabular-nums">
                    <span className={cn("num", pnlClass(u))}>
                      {u == null ? "—" : formatNumber(u, { decimals: 4, sign: true })}
                    </span>
                    <span className={cn("text-xs", pnlClass(roi))}>
                      {roi == null ? "" : `${roi.toFixed(2)}%`}
                    </span>
                  </span>
                </li>
              );
            })}
            {sorted.length > 6 ? (
              <li className="text-xs text-muted pt-1 border-t border-border/30">
                +{sorted.length - 6} további pozíció a{" "}
                <Link href="/positions" className="text-accent hover:underline">
                  Pozíciók
                </Link>{" "}
                oldalon.
              </li>
            ) : null}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function PerSymbolCard({
  rows,
}: {
  rows: { symbol: string; realized_pnl_usdt: string }[];
}) {
  const top = rows.slice(0, 8);
  const bottom = rows.slice(-5).reverse();
  return (
    <Card>
      <CardHeader>
        <CardTitle>Szimbólumonkénti realized PnL</CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
        <div>
          <h3 className="text-xs uppercase text-muted mb-2">Legjobb 8</h3>
          {top.length === 0 ? (
            <p className="text-muted">—</p>
          ) : (
            <ul className="space-y-1">
              {top.map((r) => {
                const v = num(r.realized_pnl_usdt);
                return (
                  <li
                    key={r.symbol}
                    className="flex items-center justify-between gap-2"
                  >
                    <span className="font-medium">{r.symbol}</span>
                    <span className={cn("num", pnlClass(v))}>
                      {v == null ? "—" : formatNumber(v, { decimals: 4, sign: true })}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        <div>
          <h3 className="text-xs uppercase text-muted mb-2">Legrosszabb 5</h3>
          {bottom.length === 0 ? (
            <p className="text-muted">—</p>
          ) : (
            <ul className="space-y-1">
              {bottom.map((r) => {
                const v = num(r.realized_pnl_usdt);
                return (
                  <li
                    key={`b-${r.symbol}`}
                    className="flex items-center justify-between gap-2"
                  >
                    <span className="font-medium">{r.symbol}</span>
                    <span className={cn("num", pnlClass(v))}>
                      {v == null ? "—" : formatNumber(v, { decimals: 4, sign: true })}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function RecentEventsCard({ data }: { data: DashboardSummary }) {
  const events = data.events;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Friss események (24h)</CardTitle>
        <Link href="/events" className="text-xs text-accent hover:underline">
          Eseménynapló →
        </Link>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-1.5 mb-3 text-xs">
          {Object.entries(events.by_level_24h).map(([level, count]) => (
            <span
              key={level}
              className={cn(
                "rounded border bg-bg-subtle px-2 py-0.5",
                LEVEL_COLOR[level] ?? "text-muted border-muted/40",
              )}
            >
              {level}: <span className="num">{count}</span>
            </span>
          ))}
          {events.total_24h === 0 && (
            <span className="text-muted">Nem történt esemény az elmúlt 24 órában.</span>
          )}
        </div>
        {events.recent.length === 0 ? (
          <p className="text-muted text-sm">—</p>
        ) : (
          <ul className="text-xs space-y-2">
            {events.recent.map((e) => (
              <li
                key={e.id}
                className="flex flex-col sm:flex-row gap-1 sm:gap-3 border-t border-border/30 pt-2"
              >
                <span className="text-muted whitespace-nowrap num">
                  {e.created_at
                    ? new Date(e.created_at).toLocaleString("hu-HU")
                    : "—"}
                </span>
                <span
                  className={cn(
                    "inline-block rounded px-1.5 py-0.5 text-[10px] uppercase border bg-bg-subtle",
                    LEVEL_COLOR[e.level ?? "INFO"] ?? "text-muted border-muted/40",
                  )}
                >
                  {e.level ?? "—"}
                </span>
                <span className="font-mono">{e.event}</span>
                <span className="text-muted truncate">{e.message ?? ""}</span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function Row({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "positive" | "negative" | "neutral";
}) {
  const toneClass =
    tone === "positive"
      ? "text-profit"
      : tone === "negative"
        ? "text-loss"
        : "text-slate-200";
  return (
    <div className="flex items-baseline justify-between gap-3 text-sm">
      <span className="text-muted">{label}</span>
      <span className={cn("font-medium tabular-nums", toneClass)}>{value}</span>
    </div>
  );
}
