"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { api } from "@/lib/api";
import {
  type BlackoutDayConfig,
  type TradingBlackoutSchedule,
  WEEKDAY_ORDER,
  normalizeTimeInput,
} from "@/lib/tradingBlackout";

const MODE_OPTIONS: { value: BlackoutDayConfig["mode"]; label: string }[] = [
  { value: "open", label: "Nyitott (nincs tiltás)" },
  { value: "block_all", label: "Egész nap tiltva" },
  { value: "block_ranges", label: "Tiltott idősávok" },
];

function emptyRange(): { start: string; end: string } {
  return { start: "22:00", end: "06:00" };
}

/** Szerver snapshot összehasonlítás — ne reseteljünk új objektum referenciára. */
function scheduleFingerprint(schedule: TradingBlackoutSchedule): string {
  return JSON.stringify(schedule);
}

export function TradingBlackoutEditor({
  initial,
  onSaved,
}: {
  initial: TradingBlackoutSchedule;
  onSaved?: () => void;
}) {
  const [schedule, setSchedule] = useState<TradingBlackoutSchedule>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const syncedFingerprintRef = useRef(scheduleFingerprint(initial));

  // Háttér-frissítés (WS / polling) ne írja felül a szerkesztést; mentés után szinkronizálunk.
  useEffect(() => {
    if (dirty) return;
    const fp = scheduleFingerprint(initial);
    if (fp === syncedFingerprintRef.current) return;
    syncedFingerprintRef.current = fp;
    setSchedule(initial);
  }, [initial, dirty]);

  const updateDay = useCallback(
    (dayKey: string, patch: Partial<BlackoutDayConfig>) => {
      setSchedule((prev) => ({
        ...prev,
        days: {
          ...prev.days,
          [dayKey]: { ...prev.days[dayKey], ...patch },
        },
      }));
      setDirty(true);
    },
    [],
  );

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const payload: TradingBlackoutSchedule = {
        ...schedule,
        days: Object.fromEntries(
          Object.entries(schedule.days).map(([k, d]) => [
            k,
            {
              ...d,
              block_ranges: d.block_ranges.map((r) => ({
                start: normalizeTimeInput(r.start),
                end: normalizeTimeInput(r.end),
              })),
            },
          ]),
        ),
      };
      await api.putTradingBlackout(payload);
      syncedFingerprintRef.current = scheduleFingerprint(payload);
      setSchedule(payload);
      setDirty(false);
      onSaved?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Mentés sikertelen");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted leading-relaxed">
        Csak <strong>új pozíció nyitás</strong> (OPEN) érintett — zárás és meglévő pozíciók
        kezelése továbbra is mehet. Időzóna: {schedule.timezone}.
      </p>
      {error ? (
        <p className="text-loss text-sm border border-loss/40 rounded-md px-3 py-2">
          {error}
        </p>
      ) : null}
      <div className="space-y-3">
        {WEEKDAY_ORDER.map(({ key, label }) => {
          const day = schedule.days[key] ?? { mode: "open", block_ranges: [] };
          return (
            <div
              key={key}
              className="rounded-md border border-border/60 bg-bg-card/30 p-3 space-y-2"
            >
              <div className="flex flex-wrap items-center gap-2 justify-between">
                <span className="font-medium text-slate-200 w-24">{label}</span>
                <Select
                  className="min-w-[12rem] flex-1"
                  value={day.mode}
                  onChange={(e) => {
                    const mode = e.target.value as BlackoutDayConfig["mode"];
                    if (mode === "block_ranges") {
                      updateDay(key, {
                        mode,
                        block_ranges:
                          day.block_ranges.length > 0
                            ? day.block_ranges
                            : [emptyRange()],
                      });
                    } else {
                      updateDay(key, { mode, block_ranges: [] });
                    }
                  }}
                >
                  {MODE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </Select>
              </div>
              {day.mode === "block_ranges" ? (
                <div className="space-y-2 pl-0 sm:pl-24">
                  {day.block_ranges.map((range, idx) => (
                    <div
                      key={`${key}-${idx}`}
                      className="flex flex-wrap items-center gap-2 text-sm"
                    >
                      <label className="text-xs text-muted">Tól</label>
                      <input
                        type="time"
                        className="rounded border border-border bg-bg-subtle px-2 py-1 text-slate-200"
                        value={range.start}
                        onChange={(e) => {
                          const next = [...day.block_ranges];
                          next[idx] = { ...next[idx], start: e.target.value };
                          updateDay(key, { block_ranges: next });
                        }}
                      />
                      <label className="text-xs text-muted">Ig</label>
                      <input
                        type="time"
                        className="rounded border border-border bg-bg-subtle px-2 py-1 text-slate-200"
                        value={range.end}
                        onChange={(e) => {
                          const next = [...day.block_ranges];
                          next[idx] = { ...next[idx], end: e.target.value };
                          updateDay(key, { block_ranges: next });
                        }}
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={day.block_ranges.length <= 1}
                        onClick={() => {
                          const next = day.block_ranges.filter((_, i) => i !== idx);
                          updateDay(key, { block_ranges: next });
                        }}
                      >
                        Törlés
                      </Button>
                    </div>
                  ))}
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() =>
                      updateDay(key, {
                        block_ranges: [...day.block_ranges, emptyRange()],
                      })
                    }
                  >
                    + Idősáv
                  </Button>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" disabled={busy || !dirty} onClick={() => void save()}>
          Ütemezés mentése
        </Button>
        {dirty ? (
          <span className="text-xs text-amber-400 self-center">Nem mentett változások</span>
        ) : null}
      </div>
    </div>
  );
}
