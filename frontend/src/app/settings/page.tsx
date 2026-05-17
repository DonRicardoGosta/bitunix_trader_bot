"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type SettingsSnapshot } from "@/lib/api";
import { useRefreshInterval } from "@/contexts/RefreshIntervalContext";
import { useLiveEpoch } from "@/contexts/LiveUpdatesContext";
import { TradingBlackoutEditor } from "@/components/TradingBlackoutEditor";
import {
  defaultTradingBlackoutSchedule,
  type TradingBlackoutSchedule,
} from "@/lib/tradingBlackout";
import { cn } from "@/lib/utils";

type ToggleKey =
  | "trading_paused"
  | "require_calibration_for_trading"
  | "strategy_runner_paused"
  | "bitunix_live_trading"
  | "strategy_top_signal_entries_enabled";

const TOGGLES: {
  key: ToggleKey;
  label: string;
  hint: string;
  invert?: boolean;
}[] = [
  {
    key: "trading_paused",
    label: "Trading szüneteltetve",
    hint: "Minden order (manuális + stratégia) blokkolva.",
    invert: true,
  },
  {
    key: "require_calibration_for_trading",
    label: "Kalibráció kötelező",
    hint: "Csak friss TP/SL kalibráció után enged tradelni.",
  },
  {
    key: "strategy_runner_paused",
    label: "Stratégia scheduler szünet",
    hint: "A háttér stratégia futások kihagyása.",
    invert: true,
  },
  {
    key: "bitunix_live_trading",
    label: "Élő trading (Bitunix)",
    hint: "Bekapcsolva: valódi rendelések mennek a tőzsdére. Kikapcsolva: dry-run.",
  },
  {
    key: "strategy_top_signal_entries_enabled",
    label: "Top signal entries stratégia",
    hint: "A stratégia futása és scheduler részvétele.",
  },
];

function effectiveToggle(
  eff: SettingsSnapshot["effective"],
  key: ToggleKey,
  invert?: boolean,
): boolean {
  let raw: boolean | undefined;
  if (key === "bitunix_live_trading") {
    raw = eff.live_trading;
  } else if (key === "strategy_top_signal_entries_enabled") {
    raw = eff.strategies.top_signal_entries;
  } else {
    const v = eff[key as keyof SettingsSnapshot["effective"]];
    raw = typeof v === "boolean" ? v : undefined;
  }
  if (typeof raw !== "boolean") return false;
  return invert ? !raw : raw;
}

export default function SettingsPage() {
  const { refreshIntervalMs } = useRefreshInterval();
  const settingsEpoch = useLiveEpoch("settings");
  const [snap, setSnap] = useState<SettingsSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<ToggleKey | "pause" | null>(null);

  const load = useCallback(async () => {
    try {
      const s = await api.settingsSnapshot();
      setSnap(s);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Betöltési hiba");
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(load, refreshIntervalMs);
    return () => clearInterval(id);
  }, [load, refreshIntervalMs, settingsEpoch]);

  async function patchOne(key: ToggleKey, next: boolean) {
    setBusy(key);
    try {
      await api.patchSettings({ [key]: next });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Mentés sikertelen");
    } finally {
      setBusy(null);
    }
  }

  async function quickPause(paused: boolean) {
    setBusy("pause");
    try {
      await api.setTradingPause(paused);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Művelet sikertelen");
    } finally {
      setBusy(null);
    }
  }

  const eff = snap?.effective;

  const tradingBlackoutInitial = useMemo((): TradingBlackoutSchedule => {
    if (snap?.trading_blackout) {
      return snap.trading_blackout as TradingBlackoutSchedule;
    }
    return defaultTradingBlackoutSchedule();
  }, [snap?.trading_blackout]);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-slate-100">Vezérlőpult</h1>
        <p className="text-muted text-sm mt-1">
          Runtime kapcsolók az adatbázisban — élő trading és stratégia be/ki innen vezérelhető.
        </p>
      </header>

      {error && (
        <p className="text-loss text-sm border border-loss/40 rounded-md px-3 py-2">
          {error}
        </p>
      )}

      {!snap && !error && <p className="text-muted text-sm">Betöltés…</p>}

      {snap && eff && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Trading állapot</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
                <StatusPill
                  label="Pause"
                  ok={!eff.trading_paused}
                  value={eff.trading_paused ? "IGEN" : "nem"}
                />
                <StatusPill
                  label="Live trading"
                  ok={eff.live_trading}
                  value={eff.live_trading ? "engedélyezve" : "dry-run"}
                />
                <StatusPill
                  label="Kalibráció gate"
                  ok={!eff.require_calibration_for_trading}
                  value={
                    eff.require_calibration_for_trading ? "kötelező" : "off"
                  }
                />
                <StatusPill
                  label="Scheduler"
                  ok={eff.strategy_runner_active}
                  value={eff.strategy_runner_active ? "aktív" : "szünet"}
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="primary"
                  disabled={busy !== null || eff.trading_paused}
                  onClick={() => void quickPause(true)}
                >
                  Trading pause
                </Button>
                <Button
                  variant="secondary"
                  disabled={busy !== null || !eff.trading_paused}
                  onClick={() => void quickPause(false)}
                >
                  Folytatás
                </Button>
                <Link
                  href="/calibration"
                  className="text-sm text-accent hover:underline self-center px-2"
                >
                  Kalibráció →
                </Link>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Új pozíció tiltási ütemezés</CardTitle>
              <span className="text-xs text-muted">
                {eff.new_position_open_allowed
                  ? "Most engedélyezett az új pozíció nyitás."
                  : eff.new_position_block_reason ?? "Tiltva az ütemezés szerint."}
              </span>
            </CardHeader>
            <CardContent>
              <TradingBlackoutEditor
                initial={tradingBlackoutInitial}
                onSaved={() => void load()}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Kapcsolók</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {TOGGLES.map((t) => {
                const checked = effectiveToggle(eff, t.key, t.invert);
                return (
                  <label
                    key={t.key}
                    className="flex items-start gap-3 cursor-pointer border-b border-border/30 pb-3 last:border-0"
                  >
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={checked}
                      disabled={busy !== null}
                      onChange={(e) => {
                        const on = e.target.checked;
                        void patchOne(t.key, t.invert ? !on : on);
                      }}
                    />
                    <span>
                      <span className="font-medium text-slate-200 block">
                        {t.label}
                      </span>
                      <span className="text-xs text-muted">{t.hint}</span>
                    </span>
                  </label>
                );
              })}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Stratégia effektív állapot</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="text-sm space-y-1">
                {Object.entries(eff.strategies).map(([name, enabled]) => (
                  <li key={name} className="flex justify-between gap-4">
                    <span className="font-mono text-slate-200">{name}</span>
                    <span className={cn(enabled ? "text-profit" : "text-muted")}>
                      {enabled ? "bekapcsolva" : "kikapcsolva"}
                    </span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Env + scheduler referencia</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono">
                {Object.entries({ ...snap.env, ...snap.strategy_config }).map(
                  ([k, v]) => (
                    <div
                      key={k}
                      className="flex justify-between gap-2 border-b border-border/20 py-1"
                    >
                      <dt className="text-muted">{k}</dt>
                      <dd className="text-slate-200">{String(v)}</dd>
                    </div>
                  ),
                )}
              </dl>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function StatusPill({
  label,
  value,
  ok,
}: {
  label: string;
  value: string;
  ok: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-md border px-3 py-2",
        ok ? "border-profit/40 bg-profit/5" : "border-loss/40 bg-loss/5",
      )}
    >
      <span className="text-xs text-muted uppercase">{label}</span>
      <div className={cn("font-semibold mt-0.5 block", ok ? "text-profit" : "text-loss")}>
        {value}
      </div>
    </div>
  );
}
