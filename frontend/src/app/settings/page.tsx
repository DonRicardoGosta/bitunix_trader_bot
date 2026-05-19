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
  example?: string;
  invert?: boolean;
}[] = [
  {
    key: "trading_paused",
    label: "Trading szüneteltetve",
    hint:
      "Ha be van kapcsolva, minden új order blokkolva: kézi rendelés a UI-ról és stratégia nyitások egyaránt. A meglévő pozíciók nem záródnak automatikusan.",
    example: "Bekapcsolva = „vészstop” teszt vagy karbantartás közben.",
    invert: true,
  },
  {
    key: "require_calibration_for_trading",
    label: "Kalibráció kötelező",
    hint:
      "Csak akkor enged tradelni (manuálisan és stratégiával), ha van friss, sikeres TP/SL kalibráció a beállított max. korán belül. Kikapcsolva: kalibráció nélkül is mehet order.",
    example:
      "Bekapcsolva + nincs friss kalibráció → 409 / stratégia NO_OP „calibration_missing”.",
  },
  {
    key: "strategy_runner_paused",
    label: "Stratégia scheduler szünet",
    hint:
      "A háttér scheduler továbbra is fut, de kihagyja a regisztrált stratégiák automatikus futását. Kézi „Indítás most” továbbra is működhet, ha a stratégia be van kapcsolva.",
    example: "Bekapcsolva = csak kézi indítás a Stratégiák oldalon.",
    invert: true,
  },
  {
    key: "bitunix_live_trading",
    label: "Élő trading (Bitunix)",
    hint:
      "Alapértelmezés: kikapcsolva (dry-run). Bekapcsolva: valódi place_order a Bitunix felé (API kulcs kell). Kikapcsolva: naplózás és mock válasz, nincs tőzsdei order.",
    example: "Éleshez kapcsold be + érvényes BITUNIX_API_KEY/SECRET a .env-ben.",
  },
  {
    key: "strategy_top_signal_entries_enabled",
    label: "Top signal entries stratégia",
    hint:
      "Ha ki van kapcsolva, a top_signal_entries run() azonnal kilép (NO_OP, „disabled”). A scheduler és a kézi indítás is ezt tiszteletben tartja.",
    example: "Ki = paraméterek megmaradnak, de nem nyit pozíciót; be = normál futás.",
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
                    <span className="min-w-0">
                      <span className="font-medium text-slate-200 block">
                        {t.label}
                      </span>
                      <span className="text-xs text-muted block mt-0.5 leading-relaxed">
                        {t.hint}
                      </span>
                      {t.example ? (
                        <span className="text-xs text-slate-400 block mt-1 leading-relaxed">
                          <span className="text-muted">Példa: </span>
                          {t.example}
                        </span>
                      ) : null}
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
              <span className="text-xs text-muted">
                stratégia algoritmus →{" "}
                <Link href="/strategies" className="text-accent hover:underline">
                  Stratégiák
                </Link>
              </span>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono">
                {Object.entries(snap.env).map(([k, v]) => (
                  <div
                    key={k}
                    className="flex justify-between gap-2 border-b border-border/20 py-1"
                  >
                    <dt className="text-muted">{k}</dt>
                    <dd className="text-slate-200">{String(v)}</dd>
                  </div>
                ))}
                <div className="flex justify-between gap-2 border-b border-border/20 py-1 sm:col-span-2">
                  <dt className="text-muted">strategy_interval_seconds</dt>
                  <dd className="text-slate-200">
                    {snap.strategy_config.interval_seconds}
                  </dd>
                </div>
                <div className="flex justify-between gap-2 border-b border-border/20 py-1 sm:col-span-2">
                  <dt className="text-muted">calibration_interval_seconds</dt>
                  <dd className="text-slate-200">
                    {snap.strategy_config.calibration_interval_seconds}
                  </dd>
                </div>
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
