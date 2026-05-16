"use client";

import Link from "next/link";
import { api } from "@/lib/api";
import { useRefreshInterval } from "@/contexts/RefreshIntervalContext";
import { useLiveEpoch } from "@/contexts/LiveUpdatesContext";
import { usePollingQuery } from "@/hooks/usePollingQuery";

interface State {
  trading_enabled: boolean;
  trading_paused: boolean;
  calibration_gate_open: boolean;
  latest_status: string | null;
  last_finished_at: string | null;
}

export function TradingGateBanner() {
  const { refreshIntervalMs } = useRefreshInterval();
  const calEpoch = useLiveEpoch("calibration");
  const { data: state } = usePollingQuery(
    async (): Promise<State | null> => {
      try {
        const r = await api.calibrationLatest();
        return {
          trading_enabled: r.trading_enabled,
          trading_paused: r.trading_paused ?? false,
          calibration_gate_open: r.calibration_gate_open ?? r.trading_enabled,
          latest_status: r.latest?.status ?? null,
          last_finished_at: r.latest_successful?.finished_at ?? null,
        };
      } catch {
        return null;
      }
    },
    {
      intervalMs: refreshIntervalMs,
      reloadKey: calEpoch,
    },
  );

  if (state === null) return null;

  if (!state.trading_enabled) {
    return (
      <div className="rounded-md border border-loss/50 bg-loss/10 p-4 text-sm">
        <div className="font-semibold text-loss mb-1">
          ⛔ Trading le van tiltva
          {state.trading_paused ? " (pause)" : ""}
        </div>
        <p className="text-slate-200">
          {state.trading_paused
            ? "Trading pause aktív a vezérlőpulton."
            : "Nincs friss TP/SL kalibráció (gate). Indulás után ~30–60 mp, majd óránként."}{" "}
          <Link href="/settings" className="text-accent underline">
            Vezérlőpult
          </Link>
          {" · "}
          <Link href="/calibration" className="text-accent underline">
            Kalibráció
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
      <span className="flex gap-3">
        <Link href="/settings" className="text-accent hover:underline">
          Vezérlőpult
        </Link>
        <Link href="/calibration" className="text-accent hover:underline">
          Kalibráció
        </Link>
      </span>
    </div>
  );
}
