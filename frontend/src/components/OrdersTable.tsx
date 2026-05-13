"use client";

import { useEffect, useState } from "react";
import { api, type OrderRow } from "@/lib/api";

export function OrdersTable() {
  const [rows, setRows] = useState<OrderRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const r = await api.orders();
        if (!cancelled) setRows(r);
      } catch (err) {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Hiba a rendelések lekérésekor");
      }
    }
    void load();
    const id = setInterval(load, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (error) return <p className="text-loss text-sm">{error}</p>;
  if (!rows) return <p className="text-muted text-sm">Betöltés…</p>;
  if (rows.length === 0)
    return <p className="text-muted text-sm">Még nincs feladott rendelés.</p>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-xs uppercase text-muted border-b border-border">
          <tr>
            <th className="text-left py-2 pr-3">Idő</th>
            <th className="text-left py-2 pr-3">Szimbólum</th>
            <th className="text-left py-2 pr-3">Irány</th>
            <th className="text-left py-2 pr-3">Típus</th>
            <th className="text-right py-2 pr-3">Mennyiség</th>
            <th className="text-right py-2 pr-3">Ár</th>
            <th className="text-right py-2 pr-3">Tőkeáttétel</th>
            <th className="text-left py-2 pr-3">Státusz</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-b border-border/50">
              <td className="py-2 pr-3 text-muted num">
                {new Date(r.created_at).toLocaleString("hu-HU")}
              </td>
              <td className="py-2 pr-3 font-medium">{r.symbol}</td>
              <td
                className={`py-2 pr-3 font-semibold ${r.side === "BUY" ? "text-profit" : "text-loss"}`}
              >
                {r.side}
              </td>
              <td className="py-2 pr-3">{r.type}</td>
              <td className="py-2 pr-3 text-right num">{r.quantity}</td>
              <td className="py-2 pr-3 text-right num">{r.price ?? "—"}</td>
              <td className="py-2 pr-3 text-right num">{r.leverage}x</td>
              <td className="py-2 pr-3">{r.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
