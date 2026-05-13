"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Pagination, pageSlice } from "@/components/ui/Pagination";
import { api, type OrderRow } from "@/lib/api";
import { useRefreshInterval } from "@/contexts/RefreshIntervalContext";
import { cn, formatNumber } from "@/lib/utils";

function parseDecimal(value: string | null | undefined): number | null {
  if (value == null) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function formatPnl(value: string | null | undefined): string {
  const n = parseDecimal(value);
  if (n == null) return "—";
  return `${n.toFixed(6).replace(/\.?0+$/, "")} USDT`;
}

function pnlToneClass(n: number | null): string {
  if (n == null) return "";
  if (n > 0) return "text-profit";
  if (n < 0) return "text-loss";
  return "";
}

interface SymbolGroup {
  symbol: string;
  rows: OrderRow[];
  realizedSum: number;
  unrealizedSum: number;
  openCount: number;
  closedCount: number;
  pendingCount: number;
  lastActivity: number; // ms since epoch
}

function summarizeGroup(symbol: string, rows: OrderRow[]): SymbolGroup {
  let realized = 0;
  let unrealized = 0;
  let open = 0;
  let closed = 0;
  let pending = 0;
  let last = 0;
  for (const r of rows) {
    const rp = parseDecimal(r.exchange?.realized_pnl_usdt ?? null);
    const up = parseDecimal(r.exchange?.unrealized_pnl_usdt ?? null);
    if (rp != null) realized += rp;
    if (up != null) unrealized += up;
    switch (r.exchange?.lifecycle) {
      case "open":
        open += 1;
        break;
      case "closed":
        closed += 1;
        break;
      case "pending":
        pending += 1;
        break;
    }
    const ts = new Date(r.created_at).getTime();
    if (Number.isFinite(ts) && ts > last) last = ts;
  }
  return {
    symbol,
    rows,
    realizedSum: realized,
    unrealizedSum: unrealized,
    openCount: open,
    closedCount: closed,
    pendingCount: pending,
    lastActivity: last,
  };
}

type LifecycleFilter = "all" | "open" | "closed" | "pending" | "canceled" | "unknown";
type SortKey = "recent" | "pnl_desc" | "pnl_asc" | "count_desc" | "symbol_asc";

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

export function OrdersTable() {
  const { intervalSec } = useRefreshInterval();
  const [rows, setRows] = useState<OrderRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [lifecycle, setLifecycle] = useState<LifecycleFilter>("all");
  const [sortKey, setSortKey] = useState<SortKey>("recent");
  const [pageSize, setPageSize] = useState(10);
  const [page, setPage] = useState(1);
  const [openSymbols, setOpenSymbols] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        // 500 elemig elmegyünk; ha még több kell, a backend offset-tel kérhető
        const r = await api.orders({ limit: 500 });
        if (!cancelled) {
          setRows(r);
          setError(null);
        }
      } catch (err) {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Hiba a rendelések lekérésekor");
      }
    }
    void load();
    const id = setInterval(load, intervalSec * 1000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [intervalSec]);

  const filteredRows = useMemo(() => {
    if (!rows) return [];
    const needle = search.trim().toUpperCase();
    return rows.filter((r) => {
      if (needle && !r.symbol.toUpperCase().includes(needle)) return false;
      if (lifecycle !== "all" && r.exchange?.lifecycle !== lifecycle) return false;
      return true;
    });
  }, [rows, search, lifecycle]);

  const groups = useMemo<SymbolGroup[]>(() => {
    const map = new Map<string, OrderRow[]>();
    for (const r of filteredRows) {
      const arr = map.get(r.symbol) ?? [];
      arr.push(r);
      map.set(r.symbol, arr);
    }
    const list: SymbolGroup[] = [];
    for (const [sym, list2] of map) {
      list.push(summarizeGroup(sym, list2));
    }
    const compareNumber = (a: number, b: number) => (a === b ? 0 : a > b ? 1 : -1);
    switch (sortKey) {
      case "recent":
        list.sort((a, b) => compareNumber(b.lastActivity, a.lastActivity));
        break;
      case "pnl_desc":
        list.sort((a, b) => compareNumber(b.realizedSum, a.realizedSum));
        break;
      case "pnl_asc":
        list.sort((a, b) => compareNumber(a.realizedSum, b.realizedSum));
        break;
      case "count_desc":
        list.sort((a, b) => b.rows.length - a.rows.length);
        break;
      case "symbol_asc":
        list.sort((a, b) => a.symbol.localeCompare(b.symbol));
        break;
    }
    return list;
  }, [filteredRows, sortKey]);

  // Paginálás csoportokon
  const totalGroups = groups.length;
  const visibleGroups = useMemo(
    () => pageSlice(groups, page, pageSize),
    [groups, page, pageSize],
  );
  useEffect(() => {
    // Ha a szűrés / sort miatt kevesebb lett az oldal, ugorjunk vissza
    const maxPage = Math.max(1, Math.ceil(totalGroups / pageSize));
    if (page > maxPage) setPage(1);
  }, [totalGroups, pageSize, page]);

  const toggleSymbol = (symbol: string) => {
    setOpenSymbols((prev) => {
      const next = new Set(prev);
      if (next.has(symbol)) next.delete(symbol);
      else next.add(symbol);
      return next;
    });
  };

  const allOpen = useMemo(
    () => visibleGroups.length > 0 && visibleGroups.every((g) => openSymbols.has(g.symbol)),
    [visibleGroups, openSymbols],
  );

  const toggleAll = () => {
    setOpenSymbols((prev) => {
      const next = new Set(prev);
      if (allOpen) {
        for (const g of visibleGroups) next.delete(g.symbol);
      } else {
        for (const g of visibleGroups) next.add(g.symbol);
      }
      return next;
    });
  };

  const syncWarn = rows?.find((r) => r.exchange?.sync_error)?.exchange?.sync_error ?? null;

  if (error) return <p className="text-loss text-sm">{error}</p>;
  if (!rows) return <p className="text-muted text-sm">Betöltés…</p>;

  return (
    <div className="space-y-3" data-testid="orders-table">
      {syncWarn ? (
        <p className="text-xs text-amber-600 dark:text-amber-400 border border-amber-500/30 rounded-md px-3 py-2 bg-amber-500/5">
          Bitunix szinkron: {syncWarn}
        </p>
      ) : null}

      <div className="grid grid-cols-1 sm:grid-cols-4 gap-2 items-end">
        <div className="sm:col-span-1">
          <label className="block text-xs uppercase text-muted mb-1" htmlFor="orders-search">
            Szimbólum szűrő
          </label>
          <Input
            id="orders-search"
            placeholder="pl. BTC"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs uppercase text-muted mb-1" htmlFor="orders-lifecycle">
            Életciklus
          </label>
          <Select
            id="orders-lifecycle"
            value={lifecycle}
            onChange={(e) => setLifecycle(e.target.value as LifecycleFilter)}
          >
            <option value="all">Mind</option>
            <option value="open">Nyitott</option>
            <option value="closed">Lezárt</option>
            <option value="pending">Függőben</option>
            <option value="canceled">Visszavonva</option>
            <option value="unknown">Ismeretlen</option>
          </Select>
        </div>
        <div>
          <label className="block text-xs uppercase text-muted mb-1" htmlFor="orders-sort">
            Rendezés
          </label>
          <Select
            id="orders-sort"
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
          >
            <option value="recent">Legutóbbi aktivitás</option>
            <option value="pnl_desc">PnL ↓ (top winners)</option>
            <option value="pnl_asc">PnL ↑ (top losers)</option>
            <option value="count_desc">Legtöbb rendelés</option>
            <option value="symbol_asc">Szimbólum A–Z</option>
          </Select>
        </div>
        <div>
          <label className="block text-xs uppercase text-muted mb-1" htmlFor="orders-pagesize">
            Csoportok/oldal
          </label>
          <Select
            id="orders-pagesize"
            value={pageSize}
            onChange={(e) => setPageSize(Number(e.target.value) || 10)}
          >
            {PAGE_SIZE_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <div className="flex items-center justify-between text-xs text-muted">
        <span>
          <span className="num">{totalGroups}</span> szimbólum ·{" "}
          <span className="num">{filteredRows.length}</span> rendelés
        </span>
        <Button type="button" variant="ghost" size="sm" onClick={toggleAll}>
          {allOpen ? "Mind összezár" : "Mind kinyit"}
        </Button>
      </div>

      {visibleGroups.length === 0 ? (
        <p className="text-muted text-sm">Nincs találat a szűrésre.</p>
      ) : (
        <div className="space-y-2">
          {visibleGroups.map((g) => (
            <SymbolGroupRow
              key={g.symbol}
              group={g}
              open={openSymbols.has(g.symbol)}
              onToggle={() => toggleSymbol(g.symbol)}
            />
          ))}
        </div>
      )}

      <Pagination
        page={page}
        pageSize={pageSize}
        totalItems={totalGroups}
        onPageChange={setPage}
        showTotals
      />
    </div>
  );
}

function SymbolGroupRow({
  group,
  open,
  onToggle,
}: {
  group: SymbolGroup;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="rounded-md border border-border bg-bg-card/40">
      <button
        type="button"
        className={cn(
          "w-full flex items-center gap-3 px-3 py-2 text-left",
          "hover:bg-bg-subtle/50 transition-colors rounded-t-md",
        )}
        aria-expanded={open}
        aria-controls={`group-${group.symbol}`}
        onClick={onToggle}
      >
        <span
          className={cn(
            "inline-block w-3 text-muted text-xs transition-transform",
            open ? "rotate-90" : "",
          )}
          aria-hidden
        >
          ▶
        </span>
        <span className="font-semibold text-slate-100">{group.symbol}</span>
        <span className="text-xs text-muted">
          {group.rows.length} rendelés
        </span>
        <span className="flex gap-1.5 text-[10px] uppercase">
          {group.openCount > 0 && (
            <span className="px-1.5 py-0.5 rounded bg-accent/15 text-accent border border-accent/30">
              {group.openCount} nyitott
            </span>
          )}
          {group.closedCount > 0 && (
            <span className="px-1.5 py-0.5 rounded bg-muted/15 text-muted border border-muted/30">
              {group.closedCount} lezárt
            </span>
          )}
          {group.pendingCount > 0 && (
            <span className="px-1.5 py-0.5 rounded bg-yellow-500/15 text-yellow-400 border border-yellow-500/30">
              {group.pendingCount} függőben
            </span>
          )}
        </span>
        <span className="ml-auto flex items-baseline gap-4 text-sm tabular-nums">
          <span>
            <span className="text-[10px] uppercase text-muted mr-1">Realizált</span>
            <span className={pnlToneClass(group.realizedSum)}>
              {formatNumber(group.realizedSum, { decimals: 4, sign: true })}
            </span>
          </span>
          {Math.abs(group.unrealizedSum) > 1e-9 && (
            <span>
              <span className="text-[10px] uppercase text-muted mr-1">Nyitott</span>
              <span className={pnlToneClass(group.unrealizedSum)}>
                {formatNumber(group.unrealizedSum, { decimals: 4, sign: true })}
              </span>
            </span>
          )}
        </span>
      </button>
      {open ? (
        <div
          id={`group-${group.symbol}`}
          className="border-t border-border/60 overflow-x-auto"
        >
          <OrdersInnerTable rows={group.rows} />
        </div>
      ) : null}
    </div>
  );
}

function OrdersInnerTable({ rows }: { rows: OrderRow[] }) {
  const [innerPage, setInnerPage] = useState(1);
  const innerPageSize = 10;
  const sorted = useMemo(
    () => [...rows].sort((a, b) => (a.created_at < b.created_at ? 1 : -1)),
    [rows],
  );
  const visible = pageSlice(sorted, innerPage, innerPageSize);
  return (
    <div>
      <table className="w-full text-sm">
        <thead className="text-xs uppercase text-muted bg-bg-subtle/40">
          <tr>
            <th className="text-left py-2 px-3">Idő</th>
            <th className="text-left py-2 px-3">Irány</th>
            <th className="text-left py-2 px-3">Típus</th>
            <th className="text-right py-2 px-3">Mennyiség</th>
            <th className="text-right py-2 px-3">Ár</th>
            <th className="text-right py-2 px-3">Lev.</th>
            <th className="text-left py-2 px-3">Életciklus</th>
            <th className="text-right py-2 px-3">Realizált</th>
            <th className="text-right py-2 px-3">Nyitott PnL</th>
            <th className="text-right py-2 px-3">ROI %</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((r) => {
            const ex = r.exchange;
            const roiNum = parseDecimal(ex?.roi_pct ?? null);
            return (
              <tr key={r.id} className="border-t border-border/30">
                <td className="py-1.5 px-3 text-muted num whitespace-nowrap">
                  {new Date(r.created_at).toLocaleString("hu-HU")}
                </td>
                <td
                  className={cn(
                    "py-1.5 px-3 font-semibold",
                    r.side === "BUY" ? "text-profit" : "text-loss",
                  )}
                >
                  {r.side}
                </td>
                <td className="py-1.5 px-3">{r.type}</td>
                <td className="py-1.5 px-3 text-right num">{r.quantity}</td>
                <td className="py-1.5 px-3 text-right num">{r.price ?? "—"}</td>
                <td className="py-1.5 px-3 text-right num">{r.leverage}x</td>
                <td className="py-1.5 px-3 text-muted">{ex?.lifecycle_label ?? "—"}</td>
                <td className={cn("py-1.5 px-3 text-right num", pnlToneClass(parseDecimal(ex?.realized_pnl_usdt ?? null)))}>
                  {formatPnl(ex?.realized_pnl_usdt)}
                </td>
                <td className={cn("py-1.5 px-3 text-right num", pnlToneClass(parseDecimal(ex?.unrealized_pnl_usdt ?? null)))}>
                  {formatPnl(ex?.unrealized_pnl_usdt)}
                </td>
                <td className={cn("py-1.5 px-3 text-right num font-medium", pnlToneClass(roiNum))}>
                  {ex?.roi_pct != null ? `${ex.roi_pct} %` : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {sorted.length > innerPageSize ? (
        <div className="p-2">
          <Pagination
            page={innerPage}
            pageSize={innerPageSize}
            totalItems={sorted.length}
            onPageChange={setInnerPage}
          />
        </div>
      ) : null}
    </div>
  );
}
