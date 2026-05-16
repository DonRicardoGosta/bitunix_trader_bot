"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { OrdersTable } from "@/components/OrdersTable";
import { OrdersTotalDbPnl } from "@/components/OrdersTotalDbPnl";
import { usePersistedState } from "@/hooks/usePersistedState";
import {
  LOOKBACK_PRESETS,
  STORAGE_KEYS,
  isLookbackHours,
  lookbackLabel,
} from "@/lib/lookback";

export default function OrdersPage() {
  const [lookbackHours, setLookbackHours] = usePersistedState(
    STORAGE_KEYS.ordersLookbackHours,
    6,
    isLookbackHours,
  );

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Rendelések</h1>
          <p className="text-muted text-sm mt-1">
            Saját DB napló + Bitunix szinkron · ablak: {lookbackLabel(lookbackHours)}
          </p>
        </div>
        <div>
          <label className="block text-xs uppercase text-muted mb-1" htmlFor="ord-lb">
            Visszatekintés
          </label>
          <Select
            id="ord-lb"
            value={String(lookbackHours)}
            onChange={(e) => setLookbackHours(Number(e.target.value) || 6)}
          >
            {LOOKBACK_PRESETS.map((p) => (
              <option key={p.hours} value={String(p.hours)}>
                {p.label}
              </option>
            ))}
          </Select>
        </div>
      </header>

      <OrdersTotalDbPnl lookbackHours={lookbackHours} />

      <Card>
        <CardHeader>
          <CardTitle>Rendelés napló</CardTitle>
          <span className="text-xs text-muted">
            forrás: saját Postgres napló + Bitunix history / nyitott pozíció
          </span>
          <p className="text-xs text-muted mt-2 max-w-3xl leading-relaxed">
            Ha a realizált PnL vagy az ROI üres: nyisd meg böngészőben a backend JSON-t:{" "}
            <code className="rounded bg-bg-card px-1 py-0.5 text-[11px]">
              /api/orders?debug_sync=1
            </code>{" "}
            — másold be a chatbe <strong>egy érintett sor</strong> teljes{" "}
            <code className="rounded bg-bg-card px-1 py-0.5 text-[11px]">exchange.debug</code>{" "}
            objektumát, és ha van, a tábla feletti sárga „Bitunix szinkron” üzenetet is (API kulcsot
            / secretet ne küldj).
          </p>
        </CardHeader>
        <CardContent>
          <OrdersTable lookbackHours={lookbackHours} />
        </CardContent>
      </Card>
    </div>
  );
}
