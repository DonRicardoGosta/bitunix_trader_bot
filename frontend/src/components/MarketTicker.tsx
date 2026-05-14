"use client";

import { useEffect, useMemo, useState } from "react";
import { api, type TickerInfo } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { backgroundAwareIntervalMs } from "@/contexts/RefreshIntervalContext";
import { useLiveEpoch, useLivePushConnected } from "@/contexts/LiveUpdatesContext";

interface Props {
  symbol: string;
  refreshMs?: number;
}

export function MarketTicker({ symbol, refreshMs = 5000 }: Props) {
  const [data, setData] = useState<TickerInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [documentHidden, setDocumentHidden] = useState(false);
  const pushConnected = useLivePushConnected();
  const marketEpoch = useLiveEpoch("market");

  useEffect(() => {
    if (typeof document === "undefined") return;
    const sync = () => setDocumentHidden(document.hidden);
    sync();
    document.addEventListener("visibilitychange", sync);
    return () => document.removeEventListener("visibilitychange", sync);
  }, []);

  const effectiveRefreshMs = useMemo(
    () => backgroundAwareIntervalMs(refreshMs, documentHidden),
    [refreshMs, documentHidden],
  );

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
    if (pushConnected) {
      return () => {
        cancelled = true;
      };
    }
    const id = setInterval(load, effectiveRefreshMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [symbol, effectiveRefreshMs, pushConnected, marketEpoch]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Piaci ár · {symbol}</CardTitle>
        <span className="text-xs text-muted">
          {pushConnected
            ? "Frissítés: élő WebSocket push"
            : `Frissítés ~${effectiveRefreshMs / 1000} mp-enként`}
        </span>
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
