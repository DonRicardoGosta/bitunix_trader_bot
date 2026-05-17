"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/input";
import {
  api,
  type TopSignalEntriesConfig,
  type TopSignalEntriesConfigPatch,
} from "@/lib/api";
import { cn } from "@/lib/utils";

function configFingerprint(cfg: TopSignalEntriesConfig): string {
  return JSON.stringify(cfg);
}

type FieldDef = {
  key: keyof TopSignalEntriesConfig;
  label: string;
  description: string;
  example?: string;
  type: "number" | "text" | "bool" | "select";
  options?: { value: string; label: string }[];
};

const SECTIONS: {
  title: string;
  intro?: string;
  fields: FieldDef[];
}[] = [
  {
    title: "Pozíciók és piac scan",
    intro:
      "Hány pozíciót tartunk nyitva, és mennyi szimbólumot nézünk meg a 24 órás abszolút mozgás alapján.",
    fields: [
      {
        key: "count",
        label: "Max. párhuzamos pozíció",
        description:
          "Egyszerre ennyi „slot” lehet nyitva ezzel a stratégiával (külön szimbólumokon). A scheduler minden körben addig próbál nyitni, amíg el nem éri ezt a számot, vagy elfogynak a jelöltek.",
        example: "10 → legfeljebb 10 egyidejű nyitott pozíció (pl. 10 különböző coin).",
        type: "number",
      },
      {
        key: "scan_limit_max",
        label: "Scan limit felső határ",
        description:
          "A „Scan limit” mező nem lehet ennél nagyobb. Védelmi korlát, ha véletlenül túl nagy értéket állítanál be (ticker + API terhelés).",
        example: "1000 → a scan_limit legfeljebb 1000 lehet.",
        type: "number",
      },
      {
        key: "scan_limit",
        label: "Scan limit (24h rangsor)",
        description:
          "A futures ticker lista alapján ennyi legnagyobb abszolút 24h %-os mozgást rangsorolunk. Ezután jön a kline szűrés és a belépési logika.",
        example:
          "1000 → szinte az egész piacot végignézi; 50 → csak a top 50 mozgó.",
        type: "number",
      },
      {
        key: "kline_lookahead",
        label: "Kline lookahead",
        description:
          "A rangsorolt listából csak az első N jelölthöz kérünk gyertyát (REST terhelés csökkentése). A scan_limitnél kisebb érték gyorsabb kört ad, de kihagyhat jó jeleket a lista végén.",
        example:
          "1000 + scan_limit 1000 → minden rangsoroltra jöhet kline; 40 → csak a top 40.",
        type: "number",
      },
    ],
  },
  {
    title: "Kline, belépési szűrők, cooldown",
    intro:
      "Gyertya adatok és küszöbök: mikor tekintünk egy mozgót „jelnek”, és mikor nem nyitunk újra ugyanarra.",
    fields: [
      {
        key: "kline_interval",
        label: "Kline intervallum",
        description:
          "A belépés megerősítéséhez és (WF gate nélkül) a gyertya logikához használt időkeret. WF gate bekapcsolva mellett a walk-forward elemzéshez a rendszer a lookback alapján választhat más intervallumot is.",
        example: "15m, 1h — a backend által támogatott Bitunix intervallum.",
        type: "text",
      },
      {
        key: "kline_limit",
        label: "Kline limit (gyertya / szimbólum)",
        description:
          "Szimbólumonként ennyi gyertyát töltünk le. Kell az utolsó lezárt gyertya ellenőrzéséhez és a walk-forward gate számításához.",
        example: "80 → kb. 20 óra 15m-es gyertyán; WF gate-nél a lookback is számít.",
        type: "number",
      },
      {
        key: "cooldown_minutes",
        label: "Cooldown (perc / szimbólum)",
        description:
          "Ugyanarra a szimbólumra ennyi percig nem nyit új pozíciót a stratégia (a saját korábbi orderjei alapján). WF gate után van külön WF cooldown is.",
        example: "240 = 4 óra; 0 = nincs ilyen per-stratégia cooldown.",
        type: "number",
      },
      {
        key: "min_abs_change_pct",
        label: "Minimális |24h % változás|",
        description:
          "Csak akkor jöhet szóba belépés, ha a ticker 24 órás százalékos mozgása legalább ennyi (előjel nélkül, abszolút érték).",
        example: "1.0 → legalább ±1% 24h mozgás kell; 5.0 → csak erősebb mozgók.",
        type: "text",
      },
      {
        key: "range_threshold",
        label: "24h range pozíció küszöb",
        description:
          "A 24h low–high tartományban hol van az ár. Long: a range felső részén kell lennie (legalább ennyi %-nál a low-tól). Short: az alsó részén (legfeljebb 1−küszöb).",
        example:
          "0.60 → long, ha az ár a range felső ~40%-ában; short, ha az alsó ~40%-ában.",
        type: "text",
      },
      {
        key: "max_kline_concurrency",
        label: "Max. párhuzamos kline lekérés",
        description:
          "Egy stratégia futásban egyszerre legfeljebb ennyi get_klines hívás mehet. Magasabb = gyorsabb kör, de nagyobb terhelés a Bitunix API-n.",
        example: "10 → tíz szimbólum gyertyája töltődik párhuzamosan.",
        type: "number",
      },
    ],
  },
  {
    title: "Walk-forward gate",
    intro:
      "Opcionális szűrő: csak akkor nyit, ha a coin-analyze walk-forward variáció ajánlást ad, az irány egyezik, és a TP/SL onnan jön.",
    fields: [
      {
        key: "wf_gate_enabled",
        label: "WF gate bekapcsolva",
        description:
          "Bekapcsolva: minden jelölthöz WF variációk futnak; csak ajánlott variáció + egyező irány esetén nyit. TP/SL a WF „best signal” százalékaiból számolódik (nem a kalibrációból). Kikapcsolva: klasszikus kline + kalibráció / ROI fallback.",
        example: "true = szigorúbb, kevesebb trade; false = több jel, kalibrált TP/SL.",
        type: "bool",
      },
      {
        key: "wf_lookback_minutes",
        label: "WF visszamenő ablak (perc)",
        description:
          "Ennyi percnyi múltból épül a walk-forward elemzés (tiszta lábak, variációk, ajánlás).",
        example: "4320 = 72 óra; 2880 = 48 óra.",
        type: "number",
      },
      {
        key: "wf_cooldown_minutes",
        label: "WF cooldown (perc / szimbólum)",
        description:
          "WF gate mellett: ha egy szimbólumon WF alapján már volt döntés (nyitás vagy skip), ugyanarra ennyi ideig nem nyit újra WF gate-en keresztül.",
        example: "60 = 1 óra várakozás szimbólumonként WF után.",
        type: "number",
      },
      {
        key: "wf_choppiness_max",
        label: "WF choppiness maximum",
        description:
          "A walk-forward „tiszta láb” szűrésénél a choppiness felső határa. Magasabb érték = több zajosabb láb is beleszámít (lazább szűrés).",
        example: "1.72 — alapértelmezett; kisebb érték = kevesebb, de tisztább láb.",
        type: "text",
      },
    ],
  },
  {
    title: "Margin és TP/SL fallback",
    intro:
      "Pozíciónkénti margin számítás és TP/SL, ha nincs WF jel vagy kalibrált move % — valamint ROI szűrő a belépés előtt.",
    fields: [
      {
        key: "margin_pct_of_balance",
        label: "Margin: egyenleg százaléka",
        description:
          "Pozíciónkénti margin = max(ez × elérhető USDT egyenleg, minimum margin USDT). A tényleges qty ebből és a leverage-ből jön.",
        example: "0.01 + 1000 USDT egyenleg → ~10 USDT margin / pozíció (ha a minimum nem nagyobb).",
        type: "text",
      },
      {
        key: "min_margin_usdt",
        label: "Minimum margin (USDT)",
        description:
          "Margin alsó határ pozíciónként, ha a százalékos számítás ennél kisebb lenne.",
        example: "0.2 → legalább 0,2 USDT margin minden nyitásnál.",
        type: "text",
      },
      {
        key: "tp_roi_pct",
        label: "TP ROI % (fallback)",
        description:
          "Take-profit ROI a marginon, ha nincs kalibrált / WF move % — a tpsl modul ebből számol árat.",
        example: "200 → +200% ROI a marginon TP-n (nagyon agresszív; óvatosan élesben).",
        type: "text",
      },
      {
        key: "sl_roi_pct",
        label: "SL ROI % (fallback)",
        description:
          "Stop-loss ROI a marginon fallback módban. Magas érték közelíti a likvidációt — csak tudatosan állítsd.",
        example: "100 → −100% ROI a marginon SL-n (nagyon széles stop).",
        type: "text",
      },
      {
        key: "min_tp_roi_pct",
        label: "Min. TP ROI % szűrő",
        description:
          "Belépés előtti szűrő: ha a TP move % × leverage alapján számolt implikált TP ROI kisebb ennél, a trade kimarad. 0 = kikapcsolva.",
        example:
          "60 → skip, ha a várható TP ROI a marginon 60% alatt van; 0 = nem szűr erre.",
        type: "text",
      },
      {
        key: "tpsl_stop_type",
        label: "TP/SL trigger típus",
        description:
          "Bitunix TP/SL trigger ára: mark price vagy utolsó deal ár. Mark price kevésbé érzékeny pillanatnyi spike-okra.",
        example: "MARK_PRICE — tipikus futures beállítás; LAST_PRICE = utolsó trade.",
        type: "select",
        options: [
          { value: "MARK_PRICE", label: "MARK_PRICE (mark ár)" },
          { value: "LAST_PRICE", label: "LAST_PRICE (utolsó ár)" },
        ],
      },
    ],
  },
];

function FieldHelp({ description, example }: { description: string; example?: string }) {
  return (
    <div className="mt-1 space-y-0.5">
      <p className="text-xs text-muted leading-relaxed">{description}</p>
      {example ? (
        <p className="text-xs text-slate-400 leading-relaxed">
          <span className="text-muted">Példa: </span>
          {example}
        </p>
      ) : null}
    </div>
  );
}

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
    <div className="space-y-8">
      {SECTIONS.map((section) => (
        <section key={section.title} className="space-y-4">
          <div>
            <h3 className="text-sm font-medium text-slate-200">{section.title}</h3>
            {section.intro ? (
              <p className="text-xs text-muted mt-1 leading-relaxed">{section.intro}</p>
            ) : null}
          </div>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {section.fields.map((field) => (
              <div
                key={String(field.key)}
                className={cn(
                  "rounded-md border border-border/40 bg-bg-subtle/30 p-3",
                  field.type === "bool" && "lg:col-span-2",
                )}
              >
                {field.type === "bool" ? (
                  <label
                    htmlFor={`tse-${field.key}`}
                    className="flex items-start gap-3 cursor-pointer"
                  >
                    <input
                      id={`tse-${field.key}`}
                      type="checkbox"
                      className="mt-1 shrink-0"
                      checked={draft[field.key] === "true"}
                      onChange={(e) =>
                        setField(field.key, e.target.checked ? "true" : "false")
                      }
                    />
                    <span className="min-w-0 flex-1">
                      <span className="font-medium text-slate-200 text-sm block">
                        {field.label}
                      </span>
                      <FieldHelp description={field.description} example={field.example} />
                    </span>
                  </label>
                ) : (
                  <>
                    <Label htmlFor={`tse-${field.key}`}>{field.label}</Label>
                    <FieldHelp description={field.description} example={field.example} />
                    {field.type === "select" ? (
                      <Select
                        id={`tse-${field.key}`}
                        className="mt-2"
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
                        className="num mt-2"
                        value={draft[field.key]}
                        onChange={(e) => setField(field.key, e.target.value)}
                      />
                    )}
                  </>
                )}
              </div>
            ))}
          </div>
        </section>
      ))}
      {error && <p className="text-loss text-sm">{error}</p>}
      <div className="flex flex-wrap gap-2 pt-2 border-t border-border/40">
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
