"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useRefreshInterval } from "@/contexts/RefreshIntervalContext";
import { useLiveEpoch, useLivePushConnected } from "@/contexts/LiveUpdatesContext";

interface State {
  trading_enabled: boolean;
  latest_status: string | null;
  last_finished_at: string | null;
}

export function TradingGateBanner() {
  const { refreshIntervalMs } = useRefreshInterval();
  const pushConnected = useLivePushConnected();
  const calEpoch = useLiveEpoch("calibration");
  const [state, setState] = useState<State | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const r = await api.calibrationLatest();
        if (!cancelled)
          setState({
            trading_enabled: r.trading_enabled,
            latest_status: r.latest?.status ?? null,
            last_finished_at: r.latest_successful?.finished_at ?? null,
          });
      } catch {
        if (!cancelled) setState(null);
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
  }, [refreshIntervalMs, pushConnected, calEpoch]);

  if (state === null) return null;

  if (!state.trading_enabled) {
    return (
      <div className="rounded-md border border-loss/50 bg-loss/10 p-4 text-sm">
        <div className="font-semibold text-loss mb-1">
          ⛔ Trading le van tiltva
        </div>
        <p className="text-slate-200">
          Nincs friss TP/SL kalibráció. A háttér scheduler az indulás után
          azonnal lefuttatja az első kört (~30-60 mp), majd óránként megismétli.
          Manuális indításhoz:{" "}
          <Link href="/calibration" className="text-accent underline">
            Kalibráció oldal
          </Link>
          .
        </p>
        {state.latest_status && (
          <p className="text-xs text-muted mt-2">
            Utolsó futás státusza: <span className="num">{state.latest_status}</span>
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-md border border-profit/30 bg-profit/5 p-3 text-xs flex items-center justify-between">
      <span>
        <span className="text-profit font-semibold">✓ Trading engedélyezve</span>
        {state.last_finished_at && (
          <span className="text-muted ml-2">
            – legutóbbi kalibráció: {new Date(state.last_finished_at).toLocaleString("hu-HU")}
          </span>
        )}
      </span>
      <Link href="/calibration" className="text-accent hover:underline">
        Részletek →
      </Link>
    </div>
  );
}
