"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Pagination, pageSlice } from "@/components/ui/Pagination";
import { StatCard } from "@/components/ui/StatCard";
import {
  api,
  type NormalizedPosition,
  type NormalizedPositionsResponse,
} from "@/lib/api";
import { cn, formatNumber } from "@/lib/utils";

function num(v: string | null): number | null {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function pnlClassNum(n: number | null): string {
  if (n == null) return "";
  if (n > 0) return "text-profit";
  if (n < 0) return "text-loss";
  return "";
}

type SortKey =
  | "opened_desc"
  | "opened_asc"
  | "roi_desc"
  | "roi_asc"
  | "unrealized_desc"
  | "unrealized_asc"
  | "symbol_asc";

export function PositionsTable() {
  const [data, setData] = useState<NormalizedPositionsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("opened_desc");
  const [pageSize, setPageSize] = useState(10);
  const [page, setPage] = useState(1);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const r = await api.positionsNormalized();
        if (!cancelled) {
          setData(r);
          setError(null);
        }
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof Error ? err.message : "Hiba a pozíciók lekérésekor",
          );
      }
    }
    void load();
    const id = setInterval(load, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const filtered = useMemo(() => {
    if (!data) return [] as NormalizedPosition[];
    const needle = search.trim().toUpperCase();
    const list = data.positions.filter(
      (p) => !needle || (p.symbol ?? "").includes(needle),
    );
    const cmp = (a: number | null, b: number | null) => {
      if (a == null && b == null) return 0;
      if (a == null) return 1;
      if (b == null) return -1;
      return b - a;
    };
    const sorted = [...list];
    switch (sortKey) {
      case "opened_desc":
        sorted.sort((a, b) =>
          (b.opened_at ?? "").localeCompare(a.opened_at ?? ""),
        );
        break;
      case "opened_asc":
        sorted.sort((a, b) =>
          (a.opened_at ?? "").localeCompare(b.opened_at ?? ""),
        );
        break;
      case "roi_desc":
        sorted.sort((a, b) => cmp(num(a.roi_pct), num(b.roi_pct)));
        break;
      case "roi_asc":
        sorted.sort((a, b) => cmp(num(b.roi_pct), num(a.roi_pct)));
        break;
      case "unrealized_desc":
        sorted.sort((a, b) =>
          cmp(num(a.unrealized_pnl), num(b.unrealized_pnl)),
        );
        break;
      case "unrealized_asc":
        sorted.sort((a, b) =>
          cmp(num(b.unrealized_pnl), num(a.unrealized_pnl)),
        );
        break;
      case "symbol_asc":
        sorted.sort((a, b) =>
          (a.symbol ?? "").localeCompare(b.symbol ?? ""),
        );
        break;
    }
    return sorted;
  }, [data, search, sortKey]);

  const total = filtered.length;
  const visible = pageSlice(filtered, page, pageSize);

  useEffect(() => {
    const maxPage = Math.max(1, Math.ceil(total / pageSize));
    if (page > maxPage) setPage(1);
  }, [total, pageSize, page]);

  if (error) return <p className="text-loss text-sm">{error}</p>;
  if (!data) return <p className="text-muted text-sm">Betöltés…</p>;

  const t = data.totals;
  const unrealizedNum = Number(t.unrealized_pnl_usdt);
  const realizedNum = Number(t.realized_pnl_usdt);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard label="Nyitott pozíció" value={t.count} unit="db" />
        <StatCard
          label="Foglalt margin"
          value={formatNumber(t.margin_usdt, { decimals: 4 })}
          unit="USDT"
        />
        <StatCard
          label="Nyitott PnL"
          value={formatNumber(unrealizedNum, { decimals: 4, sign: true })}
          unit="USDT"
          tone={
            unrealizedNum > 0
              ? "positive"
              : unrealizedNum < 0
                ? "negative"
                : "neutral"
          }
        />
        <StatCard
          label="Realizált (eddig)"
          value={formatNumber(realizedNum, { decimals: 4, sign: true })}
          unit="USDT"
          tone={
            realizedNum > 0
              ? "positive"
              : realizedNum < 0
                ? "negative"
                : "neutral"
          }
          hint="A jelenleg is nyitott pozíciókon eddig elszámolt PnL (pl. fee)."
        />
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>Pozíciók</CardTitle>
          <div className="flex flex-wrap items-end gap-2">
            <div>
              <label className="block text-xs uppercase text-muted mb-1" htmlFor="pos-search">
                Szimbólum
              </label>
              <Input
                id="pos-search"
                placeholder="pl. BTC"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs uppercase text-muted mb-1" htmlFor="pos-sort">
                Rendezés
              </label>
              <select
                id="pos-sort"
                value={sortKey}
                onChange={(e) => setSortKey(e.target.value as SortKey)}
                className="rounded-md bg-bg-subtle border border-border px-3 py-2 text-sm text-slate-100"
              >
                <option value="opened_desc">Megnyitva (új → régi)</option>
                <option value="opened_asc">Megnyitva (régi → új)</option>
                <option value="roi_desc">ROI ↓</option>
                <option value="roi_asc">ROI ↑</option>
                <option value="unrealized_desc">Nyitott PnL ↓</option>
                <option value="unrealized_asc">Nyitott PnL ↑</option>
                <option value="symbol_asc">Szimbólum A–Z</option>
              </select>
            </div>
            <div>
              <label className="block text-xs uppercase text-muted mb-1" htmlFor="pos-pagesize">
                Sor/oldal
              </label>
              <select
                id="pos-pagesize"
                value={pageSize}
                onChange={(e) => setPageSize(Number(e.target.value) || 10)}
                className="rounded-md bg-bg-subtle border border-border px-3 py-2 text-sm text-slate-100"
              >
                {[10, 25, 50, 100].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {total === 0 ? (
            <p className="text-muted text-sm">Nincs nyitott pozíció.</p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-xs uppercase text-muted border-b border-border">
                    <tr>
                      <th className="text-left py-2 pr-3">Szimbólum</th>
                      <th className="text-left py-2 pr-3">Irány</th>
                      <th className="text-right py-2 pr-3">Méret</th>
                      <th className="text-right py-2 pr-3">Entry</th>
                      <th className="text-right py-2 pr-3">Mark / utolsó</th>
                      <th className="text-right py-2 pr-3">Lev.</th>
                      <th className="text-right py-2 pr-3">Margin</th>
                      <th className="text-right py-2 pr-3">Nyitott PnL</th>
                      <th className="text-right py-2 pr-3">ROI %</th>
                      <th className="text-right py-2 pr-3">Liq. ár</th>
                      <th className="text-left py-2 pr-3">Megnyitva</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((p) => {
                      const unr = num(p.unrealized_pnl);
                      const roi = num(p.roi_pct);
                      return (
                        <tr
                          key={p.position_id ?? `${p.symbol}-${p.opened_at}`}
                          className="border-b border-border/40"
                        >
                          <td className="py-2 pr-3 font-medium">{p.symbol ?? "—"}</td>
                          <td
                            className={cn(
                              "py-2 pr-3 font-semibold",
                              p.side === "BUY" ? "text-profit" : "text-loss",
                            )}
                          >
                            {p.side ?? "—"}
                          </td>
                          <td className="py-2 pr-3 text-right num">{p.qty ?? "—"}</td>
                          <td className="py-2 pr-3 text-right num">{p.entry_price ?? "—"}</td>
                          <td className="py-2 pr-3 text-right num">{p.mark_price ?? "—"}</td>
                          <td className="py-2 pr-3 text-right num">
                            {p.leverage != null ? `${p.leverage}x` : "—"}
                          </td>
                          <td className="py-2 pr-3 text-right num">{p.margin ?? "—"}</td>
                          <td
                            className={cn(
                              "py-2 pr-3 text-right num",
                              pnlClassNum(unr),
                            )}
                          >
                            {unr == null
                              ? "—"
                              : formatNumber(unr, { decimals: 4, sign: true })}
                          </td>
                          <td
                            className={cn(
                              "py-2 pr-3 text-right num font-medium",
                              pnlClassNum(roi),
                            )}
                          >
                            {p.roi_pct != null ? `${p.roi_pct} %` : "—"}
                          </td>
                          <td className="py-2 pr-3 text-right num text-muted">
                            {p.liq_price ?? "—"}
                          </td>
                          <td className="py-2 pr-3 text-muted num whitespace-nowrap">
                            {p.opened_at
                              ? new Date(p.opened_at).toLocaleString("hu-HU")
                              : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="mt-3">
                <Pagination
                  page={page}
                  pageSize={pageSize}
                  totalItems={total}
                  onPageChange={setPage}
                />
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
