"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

export default function PositionsPage() {
  const [raw, setRaw] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const r = await api.positions();
        if (!cancelled) setRaw(r);
      } catch (err) {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Hiba a pozíciók lekérésekor");
      }
    }
    void load();
    const id = setInterval(load, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Nyitott pozíciók</CardTitle>
        <span className="text-xs text-muted">
          forrás: Bitunix /futures/position/get_pending_positions
        </span>
      </CardHeader>
      <CardContent>
        {error && <p className="text-loss text-sm">{error}</p>}
        {!error && !raw && <p className="text-muted text-sm">Betöltés…</p>}
        {raw !== null && (
          <pre className="text-xs bg-bg-subtle p-3 rounded-md overflow-x-auto">
            {JSON.stringify(raw, null, 2)}
          </pre>
        )}
        <p className="text-xs text-muted mt-3">
          Megjegyzés: a nyers JSON-t később egy táblázatos nézettel váltjuk ki
          (PnL színezéssel, leverage badge-dzsel).
        </p>
      </CardContent>
    </Card>
  );
}
