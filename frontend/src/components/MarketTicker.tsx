"use client";

import { useEffect, useState } from "react";
import { api, type TickerInfo } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Props {
  symbol: string;
  refreshMs?: number;
}

export function MarketTicker({ symbol, refreshMs = 5000 }: Props) {
  const [data, setData] = useState<TickerInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const t = await api.ticker(symbol);
        if (!cancelled) setData(t);
      } catch (err) {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Hiba a ticker lekérésekor");
      }
    }
    void load();
    const id = setInterval(load, refreshMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [symbol, refreshMs]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Piaci ár · {symbol}</CardTitle>
        <span className="text-xs text-muted">frissítés {refreshMs / 1000}mp-enként</span>
      </CardHeader>
      <CardContent>
        {error && <p className="text-loss text-sm">{error}</p>}
        {!error && !data && <p className="text-muted text-sm">Betöltés…</p>}
        {data && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            <Metric label="Utolsó" value={data.last_price} primary />
            <Metric label="24h Max" value={data.high_24h} />
            <Metric label="24h Min" value={data.low_24h} />
            <Metric label="24h Vol" value={data.volume_24h} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Metric({
  label,
  value,
  primary,
}: {
  label: string;
  value: string | null | undefined;
  primary?: boolean;
}) {
  return (
    <div>
      <div className="text-xs uppercase text-muted">{label}</div>
      <div className={`num ${primary ? "text-lg text-slate-50" : "text-slate-200"}`}>
        {value ?? "—"}
      </div>
    </div>
  );
}
