"use client";

import { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { usePollingQuery } from "@/hooks/usePollingQuery";
import { RefreshIndicator } from "@/components/RefreshIndicator";
import { lookbackLabel } from "@/lib/lookback";
import { ORDERS_LIFECYCLE_CLOSED } from "@/lib/ordersPage";
import { cn, formatNumber } from "@/lib/utils";

function parseNum(s: string | null | undefined): number | null {
  if (s == null) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

export function OrdersTotalDbPnl({
  lookbackHours = 6,
  refreshIntervalMs,
}: {
  lookbackHours?: number;
  refreshIntervalMs: number;
}) {
  const { data: pnlData, error, isRefreshing } = usePollingQuery(
    () => api.ordersPnlTotals(lookbackHours, ORDERS_LIFECYCLE_CLOSED),
    {
      intervalMs: refreshIntervalMs,
      staleKey: `${lookbackHours}:${refreshIntervalMs}`,
      errorMessage: "PnL összesítés lekérése sikertelen",
    },
  );

  const { totalPnl, unrealized, realized, orderCount, syncError } = useMemo(() => {
    if (!pnlData) {
      return {
        totalPnl: null,
        unrealized: null,
        realized: null,
        orderCount: null,
        syncError: null,
      };
    }
    const u = parseNum(pnlData.unrealized_pnl_usdt) ?? 0;
    const re = parseNum(pnlData.realized_pnl_usdt) ?? 0;
    const t = parseNum(pnlData.total_pnl_usdt);
    return {
      unrealized: u,
      realized: re,
      totalPnl: t ?? re + u,
      orderCount: pnlData.order_count,
      syncError: pnlData.sync_error,
    };
  }, [pnlData]);

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
        <CardTitle className="flex items-center gap-2">
          Összesített realized PnL (lezárt trade-ek)
          <RefreshIndicator active={isRefreshing} />
        </CardTitle>
        <span className="text-xs text-muted">
          Csak lezárt trade-ek az ablakban ({lookbackLabel(lookbackHours)}) — Bitunix szinkron,
          realizált PnL összesen
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
