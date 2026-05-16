"use client";

import { useMemo } from "react";
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
import {
  ORDERS_REFRESH_INTERVAL_OPTIONS,
  isOrdersRefreshIntervalSec,
  ordersRefreshLabel,
} from "@/lib/ordersPage";

export default function OrdersPage() {
  const [lookbackHours, setLookbackHours] = usePersistedState(
    STORAGE_KEYS.ordersLookbackHours,
    6,
    isLookbackHours,
  );
  const [refreshIntervalSec, setRefreshIntervalSec] = usePersistedState(
    STORAGE_KEYS.ordersRefreshIntervalSec,
    60,
    isOrdersRefreshIntervalSec,
  );

  const refreshIntervalMs = useMemo(
    () => refreshIntervalSec * 1000,
    [refreshIntervalSec],
  );

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Rendelések</h1>
          <p className="text-muted text-sm mt-1">
            Ablak: {lookbackLabel(lookbackHours)} · frissítés:{" "}
            {ordersRefreshLabel(refreshIntervalSec)}
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="block text-xs uppercase text-muted mb-1" htmlFor="ord-refresh">
              Frissítés
            </label>
            <Select
              id="ord-refresh"
              value={String(refreshIntervalSec)}
              onChange={(e) =>
                setRefreshIntervalSec(Number(e.target.value) || 60)
              }
            >
              {ORDERS_REFRESH_INTERVAL_OPTIONS.map((sec) => (
                <option key={sec} value={String(sec)}>
                  {ordersRefreshLabel(sec)}
                </option>
              ))}
            </Select>
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
        </div>
      </header>

      <OrdersTotalDbPnl
        lookbackHours={lookbackHours}
        refreshIntervalMs={refreshIntervalMs}
      />

      <Card>
        <CardHeader>
          <CardTitle>Rendelés napló</CardTitle>
          <span className="text-xs text-muted">
            forrás: saját Postgres napló + Bitunix history / nyitott pozíció
          </span>
          <p className="text-xs text-muted mt-2 max-w-3xl leading-relaxed">
            Ha a realizált PnL vagy az ROI üres: nyisd meg böngészőben a backend JSON-t:{" "}
            <code className="rounded bg-bg-card px-1 py-0.5 text-[11px]">
              /api/orders?lookback_hours={lookbackHours}&amp;debug_sync=1
            </code>{" "}
            — másold be a chatbe <strong>egy érintett sor</strong> teljes{" "}
            <code className="rounded bg-bg-card px-1 py-0.5 text-[11px]">exchange.debug</code>{" "}
            objektumát, és ha van, a tábla feletti sárga „Bitunix szinkron” üzenetet is (API
            kulcsot / secretet ne küldj).
          </p>
        </CardHeader>
        <CardContent>
          <OrdersTable
            lookbackHours={lookbackHours}
            refreshIntervalMs={refreshIntervalMs}
          />
        </CardContent>
      </Card>
    </div>
  );
}
