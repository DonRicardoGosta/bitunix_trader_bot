"use client";

import { useEffect, useState } from "react";
import { api, type OrderRow } from "@/lib/api";

function parseDecimal(value: string | null | undefined): number | null {
  if (value == null) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function formatPnl(value: string | null | undefined): string {
  const n = parseDecimal(value);
  if (n == null) return "—";
  // Vékony non-breaking space tagolóhoz, max 6 jegyű (apró pip-ek miatt).
  return `${n.toFixed(6).replace(/\.?0+$/, "")} USDT`;
}

function pnlClass(value: string | null | undefined): string {
  const n = parseDecimal(value);
  if (n == null) return "";
  if (n > 0) return "text-profit";
  if (n < 0) return "text-loss";
  return "";
}

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

  const syncWarn = rows.find((r) => r.exchange?.sync_error)?.exchange?.sync_error;

  return (
    <div className="space-y-3">
      {syncWarn ? (
        <p className="text-xs text-amber-600 dark:text-amber-400 border border-amber-500/30 rounded-md px-3 py-2 bg-amber-500/5">
          Bitunix szinkron: {syncWarn} (a „DB státusz” oszlop a saját naplónk, nem frissül
          automatikusan.)
        </p>
      ) : null}
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
              <th className="text-left py-2 pr-3">DB státusz</th>
              <th className="text-left py-2 pr-3">Pozíció</th>
              <th className="text-left py-2 pr-3">Tőzsde rendelés</th>
              <th className="text-right py-2 pr-3">Realizált PnL</th>
              <th className="text-right py-2 pr-3">Nyitott PnL</th>
              <th className="text-right py-2 pr-3">ROI %</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const ex = r.exchange;
              const roiNum = parseDecimal(ex?.roi_pct ?? null);
              const roiClass =
                roiNum == null
                  ? ""
                  : roiNum > 0
                    ? "text-profit"
                    : roiNum < 0
                      ? "text-loss"
                      : "";
              return (
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
                  <td className="py-2 pr-3 text-muted">{r.status}</td>
                  <td className="py-2 pr-3 max-w-[10rem]">{ex?.lifecycle_label ?? "—"}</td>
                  <td className="py-2 pr-3 text-muted">{ex?.order_status ?? "—"}</td>
                  <td className={`py-2 pr-3 text-right num ${pnlClass(ex?.realized_pnl_usdt)}`}>
                    {formatPnl(ex?.realized_pnl_usdt)}
                  </td>
                  <td className={`py-2 pr-3 text-right num ${pnlClass(ex?.unrealized_pnl_usdt)}`}>
                    {formatPnl(ex?.unrealized_pnl_usdt)}
                  </td>
                  <td className={`py-2 pr-3 text-right num font-medium ${roiClass}`}>
                    {ex?.roi_pct != null ? `${ex.roi_pct} %` : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
