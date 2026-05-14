"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useRefreshInterval } from "@/contexts/RefreshIntervalContext";
import { useLiveEpoch, useLivePushConnected } from "@/contexts/LiveUpdatesContext";
import { cn, formatNumber } from "@/lib/utils";

function parseNum(s: string | null | undefined): number | null {
  if (s == null) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

export function OrdersTotalDbPnl() {
  const { refreshIntervalMs } = useRefreshInterval();
  const pushConnected = useLivePushConnected();
  const pnlEpoch = useLiveEpoch("orders_pnl");
  const [error, setError] = useState<string | null>(null);
  const [totalPnl, setTotalPnl] = useState<number | null>(null);
  const [unrealized, setUnrealized] = useState<number | null>(null);
  const [realized, setRealized] = useState<number | null>(null);
  const [orderCount, setOrderCount] = useState<number | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const r = await api.ordersPnlTotals();
        if (cancelled) return;
        const u = parseNum(r.unrealized_pnl_usdt) ?? 0;
        const re = parseNum(r.realized_pnl_usdt) ?? 0;
        const t = parseNum(r.total_pnl_usdt);
        setUnrealized(u);
        setRealized(re);
        setTotalPnl(t ?? re + u);
        setOrderCount(r.order_count);
        setSyncError(r.sync_error);
        setError(null);
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof Error ? err.message : "PnL összesítés lekérése sikertelen",
          );
      }
    }
    void load();
    if (pushConnected) {
      return () => {
        cancelled = true;
      };
    }
    const id = setInterval(load, refreshIntervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [refreshIntervalMs, pushConnected, pnlEpoch]);

  const tone =
    totalPnl == null ? "neutral" : totalPnl > 0 ? "positive" : totalPnl < 0 ? "negative" : "neutral";
  const toneClass =
    tone === "positive"
      ? "text-profit"
      : tone === "negative"
        ? "text-loss"
        : "text-slate-200";

  return (
    <Card>
      <CardHeader>
        <CardTitle>Összesített PnL (saját rendelésnapló)</CardTitle>
        <span className="text-xs text-muted">
          A Postgres <code className="text-[11px]">orders</code> tábla összes sora: soronkénti
          realizált + nem realizált (Bitunix szinkron, mint a táblázatnál) — nyitott és lezárt
          együtt · frissül {intervalSec} mp-ként
        </span>
      </CardHeader>
      <CardContent className="space-y-3">
        {syncError ? (
          <p className="text-xs text-amber-400 border border-amber-500/30 rounded-md px-3 py-2 bg-amber-500/5">
            Bitunix szinkron: {syncError}
          </p>
        ) : null}
        {error ? (
          <p className="text-loss text-sm">{error}</p>
        ) : totalPnl == null ? (
          <p className="text-muted text-sm">Betöltés…</p>
        ) : (
          <div className="space-y-2">
            <div className={cn("text-3xl font-bold tabular-nums", toneClass)}>
              {formatNumber(totalPnl, { decimals: 4, sign: true })} USDT
            </div>
            <div className="text-sm text-muted flex flex-wrap gap-x-4 gap-y-1">
              <span>
                Realizált (össz. sorok):{" "}
                <span className="num text-slate-200">
                  {formatNumber(realized ?? 0, { decimals: 4, sign: true })}
                </span>
              </span>
              <span>
                Nem realizált (össz. sorok):{" "}
                <span className="num text-slate-200">
                  {formatNumber(unrealized ?? 0, { decimals: 4, sign: true })}
                </span>
              </span>
              {orderCount != null ? (
                <span>
                  Rendeléssorok: <span className="num text-slate-200">{orderCount}</span>
                </span>
              ) : null}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
