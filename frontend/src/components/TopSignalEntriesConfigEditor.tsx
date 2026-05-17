"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/input";
import {
  api,
  type TopSignalEntriesConfig,
  type TopSignalEntriesConfigPatch,
} from "@/lib/api";

function configFingerprint(cfg: TopSignalEntriesConfig): string {
  return JSON.stringify(cfg);
}

type FieldDef = {
  key: keyof TopSignalEntriesConfig;
  label: string;
  type: "number" | "text" | "bool" | "select";
  options?: { value: string; label: string }[];
};

const SECTIONS: { title: string; fields: FieldDef[] }[] = [
  {
    title: "Pozíciók és scan",
    fields: [
      { key: "count", label: "Max. párhuzamos pozíció", type: "number" },
      { key: "scan_limit_max", label: "Scan limit max", type: "number" },
      { key: "scan_limit", label: "Scan limit (24h rangsor)", type: "number" },
      { key: "kline_lookahead", label: "Kline lookahead", type: "number" },
    ],
  },
  {
    title: "Kline és cooldown",
    fields: [
      { key: "kline_interval", label: "Kline intervallum", type: "text" },
      { key: "kline_limit", label: "Kline limit (gyertya)", type: "number" },
      { key: "cooldown_minutes", label: "Cooldown (perc)", type: "number" },
      { key: "min_abs_change_pct", label: "Min. |24h %|", type: "text" },
      { key: "range_threshold", label: "Range küszöb", type: "text" },
      { key: "max_kline_concurrency", label: "Max. kline párhuzam", type: "number" },
    ],
  },
  {
    title: "Walk-forward gate",
    fields: [
      { key: "wf_gate_enabled", label: "WF gate bekapcsolva", type: "bool" },
      { key: "wf_lookback_minutes", label: "WF lookback (perc)", type: "number" },
      { key: "wf_cooldown_minutes", label: "WF cooldown (perc)", type: "number" },
      { key: "wf_choppiness_max", label: "WF choppiness max", type: "text" },
    ],
  },
  {
    title: "Margin és TP/SL fallback",
    fields: [
      { key: "margin_pct_of_balance", label: "Margin % egyenlegből", type: "text" },
      { key: "min_margin_usdt", label: "Min. margin USDT", type: "text" },
      { key: "tp_roi_pct", label: "TP ROI % (fallback)", type: "text" },
      { key: "sl_roi_pct", label: "SL ROI % (fallback)", type: "text" },
      { key: "min_tp_roi_pct", label: "Min. TP ROI % szűrő", type: "text" },
      {
        key: "tpsl_stop_type",
        label: "TP/SL trigger típus",
        type: "select",
        options: [
          { value: "MARK_PRICE", label: "MARK_PRICE" },
          { value: "LAST_PRICE", label: "LAST_PRICE" },
        ],
      },
    ],
  },
];

function toFormValue(cfg: TopSignalEntriesConfig, key: keyof TopSignalEntriesConfig): string {
  const v = cfg[key];
  if (typeof v === "boolean") return v ? "true" : "false";
  return String(v);
}

function draftFromConfig(cfg: TopSignalEntriesConfig): Record<keyof TopSignalEntriesConfig, string> {
  return Object.fromEntries(
    (Object.keys(cfg) as (keyof TopSignalEntriesConfig)[]).map((k) => [k, toFormValue(cfg, k)]),
  ) as Record<keyof TopSignalEntriesConfig, string>;
}

function parsePatch(
  draft: Record<keyof TopSignalEntriesConfig, string>,
  initial: TopSignalEntriesConfig,
): TopSignalEntriesConfigPatch {
  const patch: TopSignalEntriesConfigPatch = {};
  const intKeys: (keyof TopSignalEntriesConfig)[] = [
    "count",
    "scan_limit_max",
    "scan_limit",
    "kline_lookahead",
    "kline_limit",
    "cooldown_minutes",
    "max_kline_concurrency",
    "wf_lookback_minutes",
    "wf_cooldown_minutes",
  ];
  for (const key of Object.keys(draft) as (keyof TopSignalEntriesConfig)[]) {
    const raw = draft[key];
    const was = initial[key];
    if (key === "wf_gate_enabled") {
      const next = raw === "true";
      if (next !== was) patch.wf_gate_enabled = next;
      continue;
    }
    if (intKeys.includes(key)) {
      const next = Number.parseInt(raw, 10);
      if (Number.isNaN(next) || next === was) continue;
      (patch as Record<string, number>)[key] = next;
      continue;
    }
    if (raw !== String(was)) {
      (patch as Record<string, string>)[key] = raw;
    }
  }
  return patch;
}

export function TopSignalEntriesConfigEditor({
  initial,
  onSaved,
}: {
  initial: TopSignalEntriesConfig;
  onSaved?: () => void;
}) {
  const [baseline, setBaseline] = useState(initial);
  const [draft, setDraft] = useState(() => draftFromConfig(initial));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const syncedRef = useRef(configFingerprint(initial));

  useEffect(() => {
    if (dirty) return;
    const fp = configFingerprint(initial);
    if (fp === syncedRef.current) return;
    syncedRef.current = fp;
    setBaseline(initial);
    setDraft(draftFromConfig(initial));
  }, [initial, dirty]);

  const setField = useCallback((key: keyof TopSignalEntriesConfig, value: string) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
    setDirty(true);
  }, []);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const patch = parsePatch(draft, baseline);
      if (Object.keys(patch).length === 0) {
        setDirty(false);
        return;
      }
      const res = await api.putTopSignalEntriesConfig(patch);
      syncedRef.current = configFingerprint(res.config);
      setBaseline(res.config);
      setDraft(draftFromConfig(res.config));
      setDirty(false);
      onSaved?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Mentés sikertelen");
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setDraft(draftFromConfig(baseline));
    setDirty(false);
  }

  return (
    <div className="space-y-6">
      {SECTIONS.map((section) => (
        <div key={section.title} className="space-y-3">
          <h3 className="text-sm font-medium text-slate-200">{section.title}</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {section.fields.map((field) => (
              <div key={String(field.key)}>
                <Label htmlFor={`tse-${field.key}`}>{field.label}</Label>
                {field.type === "bool" ? (
                  <label className="flex items-center gap-2 mt-1 cursor-pointer">
                    <input
                      id={`tse-${field.key}`}
                      type="checkbox"
                      checked={draft[field.key] === "true"}
                      onChange={(e) => setField(field.key, e.target.checked ? "true" : "false")}
                    />
                    <span className="text-xs text-muted">
                      {draft[field.key] === "true" ? "bekapcsolva" : "kikapcsolva"}
                    </span>
                  </label>
                ) : field.type === "select" ? (
                  <Select
                    id={`tse-${field.key}`}
                    value={draft[field.key]}
                    onChange={(e) => setField(field.key, e.target.value)}
                  >
                    {(field.options ?? []).map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </Select>
                ) : (
                  <Input
                    id={`tse-${field.key}`}
                    type={field.type === "number" ? "number" : "text"}
                    className="num"
                    value={draft[field.key]}
                    onChange={(e) => setField(field.key, e.target.value)}
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
      {error && <p className="text-loss text-sm">{error}</p>}
      <div className="flex flex-wrap gap-2">
        <Button type="button" disabled={busy || !dirty} onClick={() => void save()}>
          {busy ? "Mentés…" : "Paraméterek mentése"}
        </Button>
        <Button type="button" variant="secondary" disabled={busy || !dirty} onClick={reset}>
          Mégse
        </Button>
      </div>
    </div>
  );
}


