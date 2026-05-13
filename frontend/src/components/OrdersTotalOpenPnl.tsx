"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useRefreshInterval } from "@/contexts/RefreshIntervalContext";
import { cn, formatNumber } from "@/lib/utils";

function parseNum(s: string | null | undefined): number | null {
  if (s == null) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

export function OrdersTotalOpenPnl() {
  const { intervalSec } = useRefreshInterval();
  const [error, setError] = useState<string | null>(null);
  const [totalPnl, setTotalPnl] = useState<number | null>(null);
  const [unrealized, setUnrealized] = useState<number | null>(null);
  const [realized, setRealized] = useState<number | null>(null);
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const r = await api.positionsNormalized();
        if (cancelled) return;
        const u = parseNum(r.totals.unrealized_pnl_usdt) ?? 0;
        const re = parseNum(r.totals.realized_pnl_usdt) ?? 0;
        setUnrealized(u);
        setRealized(re);
        setTotalPnl(u + re);
        setCount(r.totals.count);
        setError(null);
      } catch (err) {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Pozíciók lekérése sikertelen");
      }
    }
    void load();
    const id = setInterval(load, intervalSec * 1000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [intervalSec]);

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
        <CardTitle>Összesített PnL (nyitott pozíciók)</CardTitle>
        <span className="text-xs text-muted">
          Minden coin együtt: nem realizált + pozíción belüli realizált (Bitunix /normalized) ·
          frissül {intervalSec} mp-ként
        </span>
      </CardHeader>
      <CardContent>
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
                Nem realizált:{" "}
                <span className="num text-slate-200">
                  {formatNumber(unrealized ?? 0, { decimals: 4, sign: true })}
                </span>
              </span>
              <span>
                Realizált (nyitott pozíción):{" "}
                <span className="num text-slate-200">
                  {formatNumber(realized ?? 0, { decimals: 4, sign: true })}
                </span>
              </span>
              {count != null ? (
                <span>
                  Pozíciók: <span className="num text-slate-200">{count}</span>
                </span>
              ) : null}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
