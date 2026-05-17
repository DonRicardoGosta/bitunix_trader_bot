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
import {
  PRESET_BALANCED_MANY,
  PRESET_MANY_POSITIONS,
} from "@/lib/topSignalEntriesPresets";

function configFingerprint(cfg: TopSignalEntriesConfig): string {
  return JSON.stringify(cfg);
}

type FieldDef = {
  key: keyof TopSignalEntriesConfig;
  label: string;
  description: string;
  example?: string;
  /** Javasolt érték, ha minél több pozíció / kitöltés a cél. */
  recommendMany?: string;
  /** Javasolt érték WF gate mellett (kompromisszum). */
  recommendBalanced?: string;
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
      "Hány pozíciót tartunk nyitva, és mennyi szimbólumot nézünk meg a 24 órás abszolút mozgás alapján. Sok pozícióhoz: először emeld a max. párhuzamos pozíciót (egyenleg szerint), majd a kline lookahead legyen legalább 3–5× ennyi.",
    fields: [
      {
        key: "count",
        label: "Max. párhuzamos pozíció",
        description:
          "Egyszerre ennyi „slot” lehet nyitva ezzel a stratégiával (külön szimbólumokon). A scheduler minden körben addig próbál nyitni, amíg el nem éri ezt a számot, vagy elfogynak a jelöltek.",
        example: "10 → legfeljebb 10 egyidejű nyitott pozíció (pl. 10 különböző coin).",
        recommendMany:
          "30–50 (max. 100), ha van rá USDT: count × margin/pozíció. Ez a fő „hány nyitott legyen” kapcsoló.",
        recommendBalanced: "20 — több slot WF mellett is, de kezelhető kockázat.",
        type: "number",
      },
      {
        key: "scan_limit_max",
        label: "Scan limit felső határ",
        description:
          "A „Scan limit” mező nem lehet ennél nagyobb. Védelmi korlát, ha véletlenül túl nagy értéket állítanál be (ticker + API terhelés).",
        example: "1000 → a scan_limit legfeljebb 1000 lehet.",
        recommendMany: "1000",
        recommendBalanced: "1000",
        type: "number",
      },
      {
        key: "scan_limit",
        label: "Scan limit (24h rangsor)",
        description:
          "A futures ticker lista alapján ennyi legnagyobb abszolút 24h %-os mozgást rangsorolunk. Ezután jön a kline szűrés és a belépési logika.",
        example:
          "1000 → szinte az egész piacot végignézi; 50 → csak a top 50 mozgó.",
        recommendMany: "800–1000 — minél több jelölt, annál nagyobb esély slot kitöltésre.",
        recommendBalanced: "500 — elég széles háló, kisebb API terhelés mint 1000.",
        type: "number",
      },
      {
        key: "kline_lookahead",
        label: "Kline lookahead",
        description:
          "A rangsorolt listából csak az első N jelölthöz kérünk gyertyát (REST terhelés csökkentése). A scan_limitnél kisebb érték gyorsabb kört ad, de kihagyhat jó jeleket a lista végén.",
        example:
          "1000 + scan_limit 1000 → minden rangsoroltra jöhet kline; 40 → csak a top 40.",
        recommendMany:
          "count × 4–5 (pl. count=30 → 150). Sok skip lesz (WF, nincs jel, cooldown) — lookahead legyen jóval nagyobb mint count.",
        recommendBalanced: "100 (count=20 mellett ~5×). Minimum: legalább count.",
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
        recommendMany: "15m — maradhat.",
        recommendBalanced: "15m",
        type: "text",
      },
      {
        key: "kline_limit",
        label: "Kline limit (gyertya / szimbólum)",
        description:
          "Szimbólumonként ennyi gyertyát töltünk le. Kell az utolsó lezárt gyertya ellenőrzéséhez és a walk-forward gate számításához.",
        example: "80 → kb. 20 óra 15m-es gyertyán; WF gate-nél a lookback is számít.",
        recommendMany: "80 (WF bekapcsolva mellett a rendszer úgyis növelheti a fetch limitet).",
        recommendBalanced: "80",
        type: "number",
      },
      {
        key: "cooldown_minutes",
        label: "Cooldown (perc / szimbólum)",
        description:
          "Ugyanarra a szimbólumra ennyi percig nem nyit új pozíciót a stratégia (a saját korábbi orderjei alapján). WF gate után van külön WF cooldown is.",
        example: "240 = 4 óra; 0 = nincs ilyen per-stratégia cooldown.",
        recommendMany:
          "60–120 — rövidebb = több újranyitás időben (nem több egyidejű slot, de gyorsabban tölt újra).",
        recommendBalanced: "120",
        type: "number",
      },
      {
        key: "min_abs_change_pct",
        label: "Minimális |24h % változás|",
        description:
          "Csak akkor jöhet szóba belépés, ha a ticker 24 órás százalékos mozgása legalább ennyi (előjel nélkül, abszolút érték).",
        example: "1.0 → legalább ±1% 24h mozgás kell; 5.0 → csak erősebb mozgók.",
        recommendMany: "0.5 — több coin átmegy a szűrőn.",
        recommendBalanced: "0.8 — kicsit szigorúbb, még mindig több jel mint 1.0.",
        type: "text",
      },
      {
        key: "range_threshold",
        label: "24h range pozíció küszöb",
        description:
          "A 24h low–high tartományban hol van az ár. Long: a range felső részén kell lennie (legalább ennyi %-nál a low-tól). Short: az alsó részén (legfeljebb 1−küszöb).",
        example:
          "0.60 → long, ha az ár a range felső ~40%-ában; short, ha az alsó ~40%-ában.",
        recommendMany:
          "0.50–0.55 — alacsonyabb = lazább zóna = több belépés (0.60 szigorúbb).",
        recommendBalanced: "0.58",
        type: "text",
      },
      {
        key: "max_kline_concurrency",
        label: "Max. párhuzamos kline lekérés",
        description:
          "Egy stratégia futásban egyszerre legfeljebb ennyi get_klines hívás mehet. Magasabb = gyorsabb kör, de nagyobb terhelés a Bitunix API-n.",
        example: "10 → tíz szimbólum gyertyája töltődik párhuzamosan.",
        recommendMany:
          "20–30 (max. 50) — egy scheduler körben hamarabb letölti a jelölteket, több esély slot kitöltésre.",
        recommendBalanced: "20",
        type: "number",
      },
    ],
  },
  {
    title: "Walk-forward gate",
    intro:
      "Opcionális szűrő: csak akkor nyit, ha a coin-analyze walk-forward variáció ajánlást ad, az irány egyezik, és a TP/SL onnan jön. Sok pozícióhoz a WF gate a legnagyobb fékkocka — kikapcsolva vagy lazítva sokkal több nyitás lesz.",
    fields: [
      {
        key: "wf_gate_enabled",
        label: "WF gate bekapcsolva",
        description:
          "Bekapcsolva: minden jelölthöz WF variációk futnak; csak ajánlott variáció + egyező irány esetén nyit. TP/SL a WF „best signal” százalékaiból számolódik (nem a kalibrációból). Kikapcsolva: klasszikus kline + kalibráció / ROI fallback.",
        example: "true = szigorúbb, kevesebb trade; false = több jel, kalibrált TP/SL.",
        recommendMany:
          "ki (false) — legtöbb pozíció; kalibráció/ROI alapú TP-SL. Ha marad be: lazítsd a choppiness és cooldown mezőket.",
        recommendBalanced: "be (true) — minőség + WF TP/SL.",
        type: "bool",
      },
      {
        key: "wf_lookback_minutes",
        label: "WF visszamenő ablak (perc)",
        description:
          "Ennyi percnyi múltból épül a walk-forward elemzés (tiszta lábak, variációk, ajánlás).",
        example: "4320 = 72 óra; 2880 = 48 óra.",
        recommendMany: "4320 (72h) vagy 2880 (48h) — rövidebb gyorsabb, hosszabb stabilabb WF.",
        recommendBalanced: "4320",
        type: "number",
      },
      {
        key: "wf_cooldown_minutes",
        label: "WF cooldown (perc / szimbólum)",
        description:
          "WF gate mellett: ha egy szimbólumon WF alapján már volt döntés (nyitás vagy skip), ugyanarra ennyi ideig nem nyit újra WF gate-en keresztül.",
        example: "60 = 1 óra várakozás szimbólumonként WF után.",
        recommendMany: "15–30 — rövidebb = több újrapróba ugyanarra a coinra.",
        recommendBalanced: "30",
        type: "number",
      },
      {
        key: "wf_choppiness_max",
        label: "WF choppiness maximum",
        description:
          "A walk-forward „tiszta láb” szűrésénél a choppiness felső határa. Magasabb érték = több zajosabb láb is beleszámít (lazább szűrés).",
        example: "1.72 — alapértelmezett; kisebb érték = kevesebb, de tisztább láb.",
        recommendMany: "1.9–2.2 — magasabb = több WF ajánlás, több nyitás.",
        recommendBalanced: "1.85",
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
        recommendMany:
          "0 vagy 30 — sok skip „tp_roi_below_min” miatt 60-nál; 0 = kikapcsolva.",
        recommendBalanced: "40",
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

function FieldHelp({
  description,
  example,
  recommendMany,
  recommendBalanced,
}: {
  description: string;
  example?: string;
  recommendMany?: string;
  recommendBalanced?: string;
}) {
  return (
    <div className="mt-1 space-y-1">
      <p className="text-xs text-muted leading-relaxed">{description}</p>
      {example ? (
        <p className="text-xs text-slate-400 leading-relaxed">
          <span className="text-muted">Példa: </span>
          {example}
        </p>
      ) : null}
      {recommendMany ? (
        <p className="text-xs leading-relaxed text-accent/90">
          <span className="text-muted font-medium">Javaslat (sok pozíció): </span>
          {recommendMany}
        </p>
      ) : null}
      {recommendBalanced ? (
        <p className="text-xs leading-relaxed text-slate-400">
          <span className="text-muted font-medium">Javaslat (WF be, kompromisszum): </span>
          {recommendBalanced}
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

  function applyPreset(preset: TopSignalEntriesConfig) {
    setDraft(draftFromConfig(preset));
    setDirty(true);
  }

  return (
    <div className="space-y-8">
      <div className="rounded-md border border-accent/30 bg-accent/5 p-4 space-y-3">
        <div>
          <h3 className="text-sm font-medium text-slate-200">
            Beállítási útmutató — minél több pozíció
          </h3>
          <p className="text-xs text-muted mt-1 leading-relaxed">
            A tényleges plafon a <strong className="text-slate-300">max. párhuzamos pozíció</strong>{" "}
            + egyenleg (margin/pozíció). A többi mező azt szabályozza, hány jel jut el a nyitásig.
            Érdemes egy futás után a „Legutóbbi futások” skip okait nézni (WF, nincs jel, cooldown,
            tp_roi_below_min).
          </p>
          <ol className="text-xs text-muted mt-2 list-decimal list-inside space-y-1 leading-relaxed">
            <li>Állítsd a max. párhuzamos pozíciót az egyenleged szerint.</li>
            <li>Kline lookahead ≥ 3× count (inkább 4–5×).</li>
            <li>Scan limit 500–1000; max kline párhuzam 20–30.</li>
            <li>Ha kevés a nyitás: WF gate ki, vagy lazítsd a choppiness / cooldown / min_tp_roi mezőket.</li>
          </ol>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={busy}
            onClick={() => applyPreset(PRESET_MANY_POSITIONS)}
          >
            Profil: max pozíció (WF ki)
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={busy}
            onClick={() => applyPreset(PRESET_BALANCED_MANY)}
          >
            Profil: sok pozíció + WF be
          </Button>
        </div>
        <p className="text-[11px] text-muted">
          A gombok kitöltik az űrlapot; mentés csak a „Paraméterek mentése” gombbal kerül DB-be.
        </p>
      </div>

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
                      <FieldHelp
                        description={field.description}
                        example={field.example}
                        recommendMany={field.recommendMany}
                        recommendBalanced={field.recommendBalanced}
                      />
                    </span>
                  </label>
                ) : (
                  <>
                    <Label htmlFor={`tse-${field.key}`}>{field.label}</Label>
                    <FieldHelp
                      description={field.description}
                      example={field.example}
                      recommendMany={field.recommendMany}
                      recommendBalanced={field.recommendBalanced}
                    />
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
