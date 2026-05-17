"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select as UiSelect } from "@/components/ui/input";
import {
  api,
  type CandleChartRow,
  type CleanLegRow,
  type CoinAnalyzeResult,
  type HoldWindowBlock,
  type HoldWindowOptimizationInfo,
  type MarketSymbolRow,
  type TpslVariationRow,
  type WalkForwardCurrentSignal,
  type WalkForwardTpslVariations,
  type WalkForwardTradeRow,
} from "@/lib/api";

const WF_REASON_HU: Record<string, string> = {
  clean_legs_up_majority: "Tiszta lábak: több felfelé szakasz",
  clean_legs_down_majority: "Tiszta lábak: több lefelé szakasz",
  clean_legs_tie_positive_net_close: "Döntetlen lábak, nettó záró emelkedett",
  clean_legs_tie_negative_net_close: "Döntetlen lábak, nettó záró csökkent",
  clean_legs_tie_flat_close: "Döntetlen lábak, sík záró → long alapértelmezés",
};

function formatLookbackMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes} perc`;
  if (minutes % 1440 === 0) return `${minutes / 1440} nap`;
  if (minutes % 60 === 0) return `${minutes / 60} óra`;
  return `${minutes} perc`;
}

const LOOKBACK_PRESETS: { label: string; minutes: number }[] = [
  { label: "1 óra", minutes: 60 },
  { label: "4 óra", minutes: 240 },
  { label: "12 óra", minutes: 720 },
  { label: "24 óra", minutes: 1440 },
  { label: "3 nap", minutes: 4320 },
  { label: "7 nap", minutes: 10080 },
];

type ChartPoint = {
  t: number;
  c: number;
  hi: number;
  lo: number;
};

function useMainChartHighlight(result: CoinAnalyzeResult | null) {
  return useMemo(() => {
    const wf = result?.walk_forward;
    if (!wf?.enabled || wf.train_start_time_ms == null || wf.train_end_time_ms == null) return null;
    if (wf.test_start_time_ms == null || wf.test_end_time_ms == null) return null;
    return {
      trainStart: wf.train_start_time_ms,
      trainEnd: wf.train_end_time_ms,
      testStart: wf.test_start_time_ms,
      testEnd: wf.test_end_time_ms,
    };
  }, [result]);
}

function candlesToChartPoints(candles: CandleChartRow[]): ChartPoint[] {
  return candles.map((k) => ({
    t: k.time_ms,
    c: Number(k.close),
    hi: Number(k.high),
    lo: Number(k.low),
  }));
}

export default function CoinAnalyzePage() {
  const [symbols, setSymbols] = useState<MarketSymbolRow[] | null>(null);
  const [symbol, setSymbol] = useState("");
  const [lookbackMin, setLookbackMin] = useState(1440);
  const [wfCooldownMin, setWfCooldownMin] = useState(60);
  const [result, setResult] = useState<CoinAnalyzeResult | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingRun, setLoadingRun] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const rows = await api.marketSymbols();
        if (!cancelled) {
          setSymbols(rows);
          setSymbol((prev) => prev || (rows[0]?.symbol ?? ""));
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Szimbólumok betöltése sikertelen");
        }
      } finally {
        if (!cancelled) setLoadingList(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const maxLevForSymbol = useMemo(() => {
    if (!symbols || !symbol) return null;
    const row = symbols.find((s) => s.symbol === symbol);
    return row?.max_leverage ?? null;
  }, [symbols, symbol]);

  const chartHl = useMainChartHighlight(result);

  const chartData: ChartPoint[] = useMemo(() => {
    if (!result?.candles.length) return [];
    return result.candles.map((k) => ({
      t: k.time_ms,
      c: Number(k.close),
      hi: Number(k.high),
      lo: Number(k.low),
    }));
  }, [result]);

  const chartEntryTrades = useMemo(() => {
    const vars = result?.walk_forward_tpsl_variations?.variations;
    if (vars?.length) {
      const rec = vars.find((v) => v.is_recommended);
      const t = rec?.sequence?.trades ?? vars[0]?.sequence?.trades;
      if (t?.length) return t;
    }
    return result?.walk_forward_sequence?.trades ?? [];
  }, [result]);

  const runAnalyze = useCallback(async () => {
    if (!symbol.trim()) return;
    setLoadingRun(true);
    setError(null);
    try {
      const res = await api.coinAnalyze({
        symbol: symbol.trim().toUpperCase(),
        lookback_minutes: lookbackMin,
        walk_forward_cooldown_minutes: wfCooldownMin,
      });
      setResult(res);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : "Elemzés sikertelen");
    } finally {
      setLoadingRun(false);
    }
  }, [symbol, lookbackMin, wfCooldownMin]);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Coin elemzés</CardTitle>
          <p className="text-sm text-muted">
            A fő charton a teljes lookback záróvonala és a tiszta swing lábak látszanak; a kék /
            borostyán sáv az első 50% train vs. második 50% teszt idő (checkpoint: első fél vége). A
            szekvenciális szimuláció <span className="font-medium text-foreground">több TP×medián / SL×medián</span>{" "}
            kombinációval fut; a legjobb TP/(TP+SL) arányú variáció mindig kinyitva, a többi becsukható.
            Céljel: legalább egy variáció{" "}
            <span className="font-medium text-foreground">≥ 80% TP győzelem</span> az összes
            szimulált trade között (feloldatlan nem számít sikernek). A lista végén: <span className="font-medium text-foreground">jelenlegi predikció</span>{" "}
            a <span className="font-medium text-foreground">legjobb variáció</span> szorzóival.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-4 items-end">
            <div className="min-w-[12rem] flex-1">
              <label className="block text-xs text-muted mb-1">Szimbólum</label>
              {loadingList ? (
                <p className="text-sm text-muted">Betöltés…</p>
              ) : symbols?.length ? (
                <UiSelect
                  className="w-full"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                >
                  {symbols.map((s) => (
                    <option key={s.symbol} value={s.symbol}>
                      {s.symbol} (max {s.max_leverage}×)
                    </option>
                  ))}
                </UiSelect>
              ) : (
                <p className="text-sm text-rose-400">Nincs elérhető szimbólumlista.</p>
              )}
            </div>
            <div>
              <label className="block text-xs text-muted mb-1">Trade cooldown (perc)</label>
              <input
                type="number"
                min={0}
                max={10080}
                className="rounded-md border border-border bg-bg-card px-3 py-2 text-sm w-[7rem]"
                value={wfCooldownMin}
                onChange={(e) => setWfCooldownMin(Number(e.target.value) || 0)}
              />
            </div>
            <div>
              <label className="block text-xs text-muted mb-1">Lookback</label>
              <select
                className="rounded-md border border-border bg-bg-card px-3 py-2 text-sm min-w-[9rem]"
                value={lookbackMin}
                onChange={(e) => setLookbackMin(Number(e.target.value))}
              >
                {LOOKBACK_PRESETS.map((p) => (
                  <option key={p.minutes} value={p.minutes}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-muted mb-1">Max. tőkeáttétel (Bitunix)</label>
              <div className="text-sm font-mono py-2 px-3 rounded-md bg-bg-subtle border border-border/60">
                {maxLevForSymbol != null ? `${maxLevForSymbol}×` : "—"}
              </div>
            </div>
            <Button
              type="button"
              onClick={() => void runAnalyze()}
              disabled={loadingRun || !symbol.trim() || loadingList}
            >
              {loadingRun ? "Elemzés…" : "Elemzés"}
            </Button>
          </div>
          {error ? <p className="text-sm text-rose-400">{error}</p> : null}
        </CardContent>
      </Card>

      {result ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>
                {result.symbol} · {result.interval} · {result.kline_limit} gyertya
              </CardTitle>
              <p className="text-xs text-muted">
                Kért lookback: {formatLookbackMinutes(result.lookback_minutes_requested)} (
                {result.lookback_minutes_requested} perc) · gyertya:{" "}
                <span className="font-medium text-foreground">{result.interval}</span> ×{" "}
                {result.kline_limit} · choppiness ≤ {result.choppiness_max} · tiszta lábak:{" "}
                {result.clean_leg_count} / {result.all_leg_count}
              </p>
            </CardHeader>
            <CardContent>
              <AnalysisParamsBanner
                result={result}
                wfCooldownMin={wfCooldownMin}
                holdCfg={result.hold_window_optimization}
              />
              <div className="grid gap-4 md:grid-cols-3 mb-4">
                <Stat label="Medián mozgás (tiszta láb)" value={result.median_move_pct} suffix="%" />
                <Stat label="Átlag mozgás" value={result.mean_move_pct} suffix="%" />
                <Stat label="Max. leverage" value={String(result.max_leverage)} suffix="×" />
              </div>
              {chartHl ? (
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted mb-2 border border-border/40 rounded-md px-2 py-1.5 bg-bg-subtle/80">
                  <span>
                    <span className="inline-block w-2.5 h-2.5 rounded-sm bg-sky-500/40 mr-1 align-middle" />
                    Train (első 50% idő)
                  </span>
                  <span>
                    <span className="inline-block w-2.5 h-2.5 rounded-sm bg-amber-500/35 mr-1 align-middle" />
                    Teszt (második 50%)
                  </span>
                  <span className="text-amber-200">│</span> sárga: checkpoint + trade belépések
                  <span className="text-sky-300">━</span> kék: záró
                </div>
              ) : null}
              <div className="h-[420px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.5} />
                    <XAxis
                      dataKey="t"
                      type="number"
                      domain={["dataMin", "dataMax"]}
                      tickFormatter={(v) =>
                        new Date(Number(v)).toLocaleString("hu-HU", {
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })
                      }
                      stroke="#94a3b8"
                      fontSize={11}
                    />
                    <YAxis
                      domain={["auto", "auto"]}
                      orientation="right"
                      width={72}
                      stroke="#94a3b8"
                      fontSize={11}
                      tickFormatter={(v) => Number(v).toLocaleString("hu-HU", { maximumFractionDigits: 6 })}
                    />
                    <Tooltip
                      labelFormatter={(v) => new Date(Number(v)).toLocaleString("hu-HU")}
                      formatter={(value: number) => [value.toLocaleString("hu-HU", { maximumFractionDigits: 8 }), "Záró"]}
                    />
                    <Legend />
                    {chartHl ? (
                      <>
                        <ReferenceArea
                          x1={chartHl.trainStart}
                          x2={chartHl.trainEnd}
                          fill="rgba(59,130,246,0.08)"
                          stroke="none"
                          ifOverflow="visible"
                        />
                        <ReferenceArea
                          x1={chartHl.testStart}
                          x2={chartHl.testEnd}
                          fill="rgba(245,158,11,0.07)"
                          stroke="none"
                          ifOverflow="visible"
                        />
                      </>
                    ) : null}
                    {result.clean_legs.map((leg: CleanLegRow, i: number) => (
                      <ReferenceArea
                        key={`${leg.start_time_ms}-${leg.end_time_ms}-${i}`}
                        x1={leg.start_time_ms}
                        x2={leg.end_time_ms}
                        fill={leg.direction === "up" ? "rgba(34,197,94,0.12)" : "rgba(248,113,113,0.12)"}
                        stroke="none"
                        ifOverflow="visible"
                      />
                    ))}
                    {result.walk_forward.enabled &&
                    result.walk_forward.checkpoint_time_ms != null ? (
                      <ReferenceLine
                        x={result.walk_forward.checkpoint_time_ms}
                        stroke="#fbbf24"
                        strokeWidth={2}
                        strokeDasharray="4 4"
                        label={{ value: "Checkpoint", fill: "#fbbf24", fontSize: 10 }}
                      />
                    ) : null}
                    {chartEntryTrades.map((tr) => (
                      <ReferenceLine
                        key={`ent-${tr.trade_index}-${tr.entry_time_ms}`}
                        x={tr.entry_time_ms}
                        stroke="#fde68a"
                        strokeWidth={1}
                        strokeDasharray="2 3"
                      />
                    ))}
                    <Line
                      name="Záró"
                      type="monotone"
                      dataKey="c"
                      stroke="#38bdf8"
                      strokeWidth={1.5}
                      dot={false}
                      isAnimationActive={false}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              <p className="text-xs text-muted mt-2">
                Halvány zöld/piros: tiszta swing lábak. Kék/borostyán: train vs teszt (50% idő). A
                vékony sárga függőlegesek a szekvenciális trade belépések; TP/SL részletek a lenti
                kis chartokon.
              </p>
              <TpslVariationsSection
                candles={result.candles}
                block={result.walk_forward_tpsl_variations}
                holdCfg={result.hold_window_optimization}
              />
              <CurrentSignalPanel
                sig={
                  result.walk_forward_tpsl_variations.best_current_signal ??
                  result.walk_forward_sequence.current_signal
                }
              />
              <WalkForwardCard wf={result.walk_forward} />
            </CardContent>
          </Card>

          {result.clean_legs.length ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Tiszta swing lábak</CardTitle>
              </CardHeader>
              <CardContent className="overflow-x-auto">
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="text-left text-muted border-b border-border">
                      <th className="py-2 pr-3">Irány</th>
                      <th className="py-2 pr-3">Mozgás %</th>
                      <th className="py-2 pr-3">Choppiness</th>
                      <th className="py-2 pr-3">Kezdés</th>
                      <th className="py-2">Vég</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.clean_legs.map((leg) => (
                      <tr key={`${leg.start_time_ms}-${leg.end_time_ms}`} className="border-b border-border/40">
                        <td className="py-1.5 pr-3">{leg.direction === "up" ? "↑ Fel" : "↓ Le"}</td>
                        <td className="py-1.5 pr-3 font-mono">{leg.move_pct}%</td>
                        <td className="py-1.5 pr-3 font-mono">{leg.choppiness}</td>
                        <td className="py-1.5 pr-3 text-xs text-muted">
                          {new Date(leg.start_time_ms).toLocaleString("hu-HU")}
                        </td>
                        <td className="py-1.5 text-xs text-muted">
                          {new Date(leg.end_time_ms).toLocaleString("hu-HU")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function TradeMiniChart({ candles, trade }: { candles: CandleChartRow[]; trade: WalkForwardTradeRow }) {
  const pts = useMemo(
    () => candlesToChartPoints(candles.slice(trade.chart_from_index, trade.chart_to_index + 1)),
    [candles, trade],
  );
  if (pts.length < 2) return null;
  const entry = Number(trade.entry_price);
  const tp = Number(trade.tp_price);
  const sl = Number(trade.sl_price);
  const entLine = [
    { t: trade.entry_time_ms, y: entry },
    { t: trade.exit_time_ms, y: entry },
  ];
  const tpLine = [
    { t: trade.entry_time_ms, y: tp },
    { t: trade.exit_time_ms, y: tp },
  ];
  const slLine = [
    { t: trade.entry_time_ms, y: sl },
    { t: trade.exit_time_ms, y: sl },
  ];
  const touchLabel =
    trade.first_touch === "tp" ? "TP" : trade.first_touch === "sl" ? "SL" : "nincs találat";
  return (
    <div className="rounded-lg border border-border/60 bg-bg-subtle/50 p-2">
      <div className="text-xs font-medium mb-1 flex flex-wrap justify-between gap-1">
        <span>#{trade.trade_index + 1}</span>
        <span className="text-muted font-normal">
          {trade.predicted_side === "long" ? "Long" : "Short"} → {touchLabel}
          {trade.strategy_would_win ? (
            <span className="text-emerald-400 ml-1">nyert</span>
          ) : trade.first_touch === "sl" ? (
            <span className="text-rose-400 ml-1">SL</span>
          ) : null}
        </span>
      </div>
      <div className="h-[200px] w-full min-w-0">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={pts} margin={{ top: 4, right: 4, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.35} />
            <XAxis
              dataKey="t"
              type="number"
              domain={["dataMin", "dataMax"]}
              tick={{ fontSize: 9 }}
              tickFormatter={(v) =>
                new Date(Number(v)).toLocaleTimeString("hu-HU", { hour: "2-digit", minute: "2-digit" })
              }
              stroke="#64748b"
            />
            <YAxis
              domain={["auto", "auto"]}
              orientation="right"
              width={56}
              tick={{ fontSize: 9 }}
              stroke="#64748b"
              tickFormatter={(v) => Number(v).toLocaleString("hu-HU", { maximumFractionDigits: 6 })}
            />
            <Tooltip
              labelFormatter={(v) => new Date(Number(v)).toLocaleString("hu-HU")}
              formatter={(v: number) => [v.toLocaleString("hu-HU", { maximumFractionDigits: 8 }), ""]}
            />
            <ReferenceLine x={trade.entry_time_ms} stroke="#fbbf24" strokeDasharray="3 3" />
            <Line data={tpLine} dataKey="y" type="linear" stroke="#4ade80" strokeDasharray="4 3" dot={false} isAnimationActive={false} />
            <Line data={slLine} dataKey="y" type="linear" stroke="#fb7185" strokeDasharray="4 3" dot={false} isAnimationActive={false} />
            <Line data={entLine} dataKey="y" type="linear" stroke="#facc15" strokeDasharray="5 3" dot={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="c" stroke="#38bdf8" strokeWidth={1.2} dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function TpslVariationsSection({
  candles,
  block,
  holdCfg,
}: {
  candles: CandleChartRow[];
  block: WalkForwardTpslVariations;
  holdCfg: HoldWindowOptimizationInfo;
}) {
  if (!block.variations.length) {
    return (
      <div className="rounded-lg border border-border/50 bg-bg-subtle/40 px-3 py-3 mt-4 text-sm text-muted">
        {block.disabled_reason === "no_variations_evaluated"
          ? "TP/SL variációk: nincs kiértékelhető rács."
          : "Nincs TP/SL variációs eredmény."}
      </div>
    );
  }
  return (
    <div className="mt-4 space-y-2">
      <div className="text-sm font-medium">TP / SL variációk (train tiszta-láb medián × szorzó)</div>
      <p className="text-xs text-muted">
        A szimulációban a medián×szorzóból számolt TP/SL %% csak <span className="font-medium text-foreground">felülről</span>{" "}
        vágódik (TP legfeljebb {block.variation_tp_move_pct_max}%, SL legfeljebb {block.variation_sl_move_pct_max}%), hogy a
        rács sorai ne essenek össze egyetlen 30/10-es értékre; az effektív SL %% soha nem nagyobb a TP %%-nál. A{" "}
        <span className="font-medium text-foreground">≥{block.variation_tp_move_pct_min}% TP</span> és{" "}
        <span className="font-medium text-foreground">≥{block.variation_sl_move_pct_min}% SL</span> az{" "}
        <span className="font-medium text-foreground">első belépés</span> nyers százalékaira vonatkozik (profil
        jelző a sorban); az ajánláshoz kell ez is. Minden kombináció ugyanazzal
        a szekvenciális szabállyal fut (50% kezdő train → trade →{" "}
        {block.variations[0]?.sequence.cooldown_minutes ?? "—"} perc cooldown → újra). Egy trade előretekintése legfeljebb a
        hátralévő gyertyák harmada (legalább 16 gyertya). A sorrend:{" "}
        <span className="font-medium text-foreground">TP / összes trade</span> csökkenő (min.{" "}
        {block.min_resolved_trades} trade). Cél: ≥{block.target_tp_win_rate_pct}% TP nyerés.
        {block.any_variation_meets_target ? (
          <span className="text-emerald-400 font-medium ml-1">Van olyan pont, ami eléri a célt.</span>
        ) : (
          <span className="text-muted ml-1">
            Egyik rács-pont sem éri el a {block.target_tp_win_rate_pct}%-ot.
          </span>
        )}{" "}
        <span className="block mt-1">
          Olyan variáció nincs a listában, ahol az utolsó {block.lookback_hours ?? 48} órában pontosan egy belépés volt,
          és sem TP, sem SL nem következett be. Legfeljebb{" "}
          <span className="font-medium text-foreground">egy ajánlott</span> konfiguráció van: a legjobb TP% azok közül,
          ahol az utolsó {block.lookback_hours ?? 48} órában legalább{" "}
          {block.min_trades_last_48h_for_recommendation} belépés történt, eléri a cél TP%-ot, és az első belépés nyers
          TP/SL %% eléri a fenti minimumot; a jelenlegi predikció csak ilyenkor a javasolt szorzókat mutatja.
        </span>
        {holdCfg.enabled ? (
          <span className="block mt-1 text-sky-300/90">
            Hold-window: a variációk sorrendje a „jó tartási idő” arány szerint is súlyozott (≥
            {holdCfg.profit_threshold_pct}% ár-mozgás profit időzített záráskor). A javasolt perc a rácsban zöld
            sorral.
          </span>
        ) : null}
      </p>
      {block.variations.map((v: TpslVariationRow, i: number) => {
        const s = v.sequence.summary;
        const stats = s ? (
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted pt-1">
            <span>
              Trade: <strong className="text-foreground">{s.total_trades}</strong>
            </span>
            <span className="text-emerald-400">TP: {s.tp_wins}</span>
            <span className="text-rose-400">SL: {s.sl_losses}</span>
            <span>feloldatlan: {s.no_result}</span>
            <span>
              TP/összes:{" "}
              <strong className="text-foreground">{v.resolved_tp_win_rate_pct ?? "—"}%</strong>
            </span>
            <span>48h belépés: {v.trades_entered_last_48h_count}</span>
            {v.first_trade_tp_move_pct_raw != null ? (
              <span>
                1. belépés nyers: TP {v.first_trade_tp_move_pct_raw}% / SL {v.first_trade_sl_move_pct_raw ?? "—"}%
              </span>
            ) : null}
            {v.meets_min_tpsl_pct_profile ? (
              <span className="text-sky-400/95">profil ≥ min</span>
            ) : (
              <span className="text-muted">profil &lt; min</span>
            )}
            {v.is_recommended ? (
              <span className="text-emerald-400 font-medium">ajánlott</span>
            ) : null}
            {v.meets_target ? (
              <span className="text-emerald-400 font-medium">≥ {block.target_tp_win_rate_pct}%</span>
            ) : null}
            {v.best_hold_minutes != null ? (
              <span className="text-sky-300">
                hold: <strong className="text-foreground">{v.best_hold_minutes} perc</strong>
                {v.hold_good_rate_pct != null ? ` (${v.hold_good_rate_pct}% jó)` : ""}
              </span>
            ) : null}
          </div>
        ) : (
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted pt-1">
            <span>48h belépés: {v.trades_entered_last_48h_count}</span>
            {v.first_trade_tp_move_pct_raw != null ? (
              <span>
                1. belépés nyers: TP {v.first_trade_tp_move_pct_raw}% / SL {v.first_trade_sl_move_pct_raw ?? "—"}%
              </span>
            ) : null}
            {v.meets_min_tpsl_pct_profile ? (
              <span className="text-sky-400/95">profil ≥ min</span>
            ) : (
              <span className="text-muted">profil &lt; min</span>
            )}
            {v.is_recommended ? (
              <span className="text-emerald-400 font-medium">ajánlott</span>
            ) : null}
            {v.best_hold_minutes != null ? (
              <span className="text-sky-300">
                hold: <strong className="text-foreground">{v.best_hold_minutes} perc</strong>
                {v.hold_good_rate_pct != null ? ` (${v.hold_good_rate_pct}% jó)` : ""}
              </span>
            ) : null}
          </div>
        );
        const charts =
          v.sequence.trades.length > 0 ? (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 pt-2">
              {v.sequence.trades.map((tr) => (
                <TradeMiniChart key={`${v.rank}-${tr.trade_index}`} candles={candles} trade={tr} />
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted pt-2">Nincs trade ebben a variációban.</p>
          );
        const head = (
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="font-medium text-foreground">{v.label}</span>
            <span className="text-xs font-mono text-muted">
              #{v.rank + 1} · TP×{v.tp_median_multiplier} SL×{v.sl_median_multiplier}
            </span>
          </div>
        );
        if (i === 0) {
          return (
            <div
              key={`wf-var-${v.rank}`}
              className="rounded-lg border border-emerald-500/40 bg-emerald-950/25 p-3 space-y-1"
            >
              <div className="text-[11px] font-semibold uppercase tracking-wide text-emerald-300/95">
                {block.has_recommended_variation && v.is_recommended
                  ? `Ajánlott konfig (≥${block.min_trades_last_48h_for_recommendation} belépés / utolsó ${block.lookback_hours ?? 48}h)`
                  : block.has_recommended_variation
                    ? "Legjobb TP% a listában — az ajánlott más sorban van (jelölve)"
                    : `Legjobb TP% sorrend — nincs ${block.lookback_hours ?? 48}h aktivitás alapú ajánlás`}
              </div>
              {head}
              {stats}
              {v.hold_window?.enabled ? <HoldWindowGridTable block={v.hold_window} /> : null}
              {charts}
            </div>
          );
        }
        return (
          <details
            key={`wf-var-${v.rank}`}
            className="rounded-lg border border-border/60 bg-bg-subtle/30 group [&_summary::-webkit-details-marker]:hidden"
          >
            <summary className="cursor-pointer select-none list-none px-3 py-2.5 flex flex-wrap items-center justify-between gap-2 hover:bg-bg-subtle/55 rounded-t-lg">
              <span className="text-sm text-foreground">{v.label}</span>
              <span className="text-xs font-mono text-muted">
                TP% {v.resolved_tp_win_rate_pct ?? "—"}
                {v.meets_target ? <span className="text-emerald-400 ml-2">cél OK</span> : null}
                {v.best_hold_minutes != null ? (
                  <span className="text-sky-300 ml-2">hold {v.best_hold_minutes}p</span>
                ) : null}
              </span>
            </summary>
            <div className="px-3 pb-3 border-t border-border/40">
              {stats}
              {v.hold_window?.enabled ? <HoldWindowGridTable block={v.hold_window} /> : null}
              {charts}
            </div>
          </details>
        );
      })}
    </div>
  );
}

function CurrentSignalPanel({ sig }: { sig: WalkForwardCurrentSignal }) {
  return (
    <div className="rounded-lg border border-emerald-500/25 bg-emerald-500/5 px-3 py-3 mt-4">
      <div className="text-sm font-medium text-emerald-100/90">Jelenlegi predikció (utolsó záró)</div>
      {!sig.enabled ? (
        <p className="text-xs text-muted mt-1">{sig.disabled_reason ?? "Nem számolható."}</p>
      ) : (
        <div className="mt-2 text-sm space-y-1">
          <p>
            Irány:{" "}
            <span className="font-mono font-semibold">
              {sig.predicted_side === "long" ? "Long (BUY)" : "Short (SELL)"}
            </span>
          </p>
          <p className="text-xs text-muted">
            {(sig.prediction_reason && WF_REASON_HU[sig.prediction_reason]) ?? sig.prediction_reason}
          </p>
          <p className="text-xs font-mono">
            Belépés: {sig.entry_price} · TP: {sig.tp_price} · SL: {sig.sl_price} · train medián:{" "}
            {sig.median_move_pct_train}% · TP távolság: {sig.tp_move_pct}% · SL távolság:{" "}
            {sig.sl_move_pct ?? "—"}% · train gyertyák: {sig.train_bar_count}
          </p>
        </div>
      )}
    </div>
  );
}

function AnalysisParamsBanner({
  result,
  wfCooldownMin,
  holdCfg,
}: {
  result: CoinAnalyzeResult;
  wfCooldownMin: number;
  holdCfg: HoldWindowOptimizationInfo;
}) {
  return (
    <div className="rounded-lg border border-border/60 bg-bg-subtle/50 px-3 py-2.5 mb-4 text-xs space-y-1.5">
      <div className="font-medium text-foreground text-sm">Elemzés futási paraméterek</div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-muted">
        <span>
          Lookback:{" "}
          <strong className="text-foreground">
            {formatLookbackMinutes(result.lookback_minutes_requested)}
          </strong>
        </span>
        <span>
          Gyertya:{" "}
          <strong className="text-foreground">
            {result.interval} × {result.kline_limit}
          </strong>
        </span>
        <span>
          WF cooldown: <strong className="text-foreground">{wfCooldownMin} perc</strong>
        </span>
      </div>
      {holdCfg.enabled ? (
        <p className="text-sky-300/95">
          Hold-window optimalizálás:{" "}
          <strong className="text-foreground">
            {holdCfg.min_minutes}–{holdCfg.max_minutes} perc, lépés {holdCfg.step_minutes} perc
          </strong>
          {" · "}
          „jó” trade küszöb: ≥{holdCfg.profit_threshold_pct}% ár-mozgás profit (TP érintés mindig jó).
          Az alábbi variációknál látszik a rács és a javasolt tartási idő.
        </p>
      ) : (
        <p className="text-muted">
          Hold-window optimalizálás ki van kapcsolva (Stratégiák → top_signal_entries). Bekapcsolva
          minden variációnál megjelenik, melyik tartási idő (perc) adná a legtöbb jó trade-et.
        </p>
      )}
    </div>
  );
}

function HoldWindowGridTable({ block }: { block: HoldWindowBlock }) {
  if (!block.enabled || !block.rows.length) return null;
  return (
    <div className="overflow-x-auto mt-2">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="text-left text-muted border-b border-border/60">
            <th className="py-1.5 pr-3">Tartás (perc)</th>
            <th className="py-1.5 pr-3">Trade-ek</th>
            <th className="py-1.5 pr-3">Jó</th>
            <th className="py-1.5">Jó arány</th>
          </tr>
        </thead>
        <tbody>
          {block.rows.map((row) => {
            const isBest = block.best_hold_minutes === row.hold_minutes;
            return (
              <tr
                key={row.hold_minutes}
                className={
                  isBest
                    ? "border-b border-emerald-500/30 bg-emerald-950/20"
                    : "border-b border-border/30"
                }
              >
                <td className="py-1 pr-3 font-mono">
                  {row.hold_minutes}
                  {isBest ? (
                    <span className="ml-1 text-emerald-400 font-sans font-medium">← legjobb</span>
                  ) : null}
                </td>
                <td className="py-1 pr-3 font-mono">{row.trades_evaluated}</td>
                <td className="py-1 pr-3 font-mono">{row.good_trades}</td>
                <td className="py-1 font-mono">
                  {row.good_rate_pct != null ? `${row.good_rate_pct}%` : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Stat({ label, value, suffix }: { label: string; value: string | null; suffix: string }) {
  return (
    <div className="rounded-lg border border-border/60 bg-bg-subtle px-3 py-2">
      <div className="text-xs text-muted">{label}</div>
      <div className="text-lg font-semibold font-mono">
        {value != null ? `${value}${suffix}` : "—"}
      </div>
    </div>
  );
}

function WalkForwardCard({ wf }: { wf: CoinAnalyzeResult["walk_forward"] }) {
  const agg = wf.aggregate;
  const aggBlock =
    agg && agg.total_runs > 0 ? (
      <div className="border-t border-border/50 pt-3 mt-3 space-y-1">
        <div className="text-xs font-medium text-muted">
          Robusztusság: {agg.total_runs} további időbeli vágás (kb. 36–60% train arány, a 50%-os
          fő forgatókönyv nélkül)
        </div>
        <p className="text-xs text-muted">
          TP előbb: <span className="font-mono text-foreground">{agg.tp_first_count}</span> · SL
          előbb: <span className="font-mono text-foreground">{agg.sl_first_count}</span> · egyik sem:{" "}
          <span className="font-mono text-foreground">{agg.no_touch_count}</span>
        </p>
        <p className="text-xs">
          <span className="text-muted">TP vs SL győzelem (ha már TP vagy SL döntött):</span>{" "}
          <span className="font-mono font-semibold text-foreground">
            {agg.strategy_win_rate_pct != null ? `${agg.strategy_win_rate_pct}%` : "—"}
          </span>
          <span className="text-muted"> · iránytalálat aránya:</span>{" "}
          <span className="font-mono font-semibold text-foreground">
            {agg.direction_hit_rate_pct != null ? `${agg.direction_hit_rate_pct}%` : "—"}
          </span>
          <span className="text-muted"> ({agg.direction_correct_count}/{agg.total_runs})</span>
        </p>
      </div>
    ) : null;

  if (!wf.enabled) {
    return (
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-3 mt-4">
        <div className="text-sm font-medium text-amber-200/90">Walk-forward (50% train → teszt)</div>
        <p className="text-xs text-muted mt-1">
          {wf.disabled_reason === "too_few_candles_or_bad_time_span"
            ? "Túl kevés gyertya vagy érvénytelen időtartomány — bővítsd a lookbacket."
            : wf.disabled_reason === "no_median_clean_legs_in_train"
              ? "Az első fél időben nem volt számolható medián a tiszta swing lábakból — nincs TP/SL távolság a fő forgatókönyvhöz."
              : wf.disabled_reason ?? "A fő (50%) szimuláció nem futtatható."}
        </p>
        {wf.train_bar_count > 0 ? (
          <p className="text-xs text-muted mt-1">
            Train gyertyák: {wf.train_bar_count} · teszt: {wf.test_bar_count}
          </p>
        ) : null}
        {aggBlock}
      </div>
    );
  }

  const reasonHu =
    (wf.prediction_reason && WF_REASON_HU[wf.prediction_reason]) ?? wf.prediction_reason ?? "—";
  const touchLabel =
    wf.first_touch === "tp"
      ? "Take profit"
      : wf.first_touch === "sl"
        ? "Stop loss"
        : wf.first_touch === "none"
          ? "Egyik sem (teszt ablak vége)"
          : "—";
  const sideHu = (s: string | null) =>
    s === "long" ? "Long (BUY)" : s === "short" ? "Short (SELL)" : "—";
  const win = wf.strategy_would_win === true;
  const hitSl = wf.first_touch === "sl";
  const hitNone = wf.first_touch === "none";

  return (
    <div className="rounded-lg border border-border/60 bg-bg-subtle px-3 py-3 mt-4 space-y-3">
      <div>
        <div className="text-sm font-medium">Walk-forward — fő forgatókönyv (50% idő: train → teszt)</div>
        <p className="text-xs text-muted mt-1">
          Az első 50% idő train ablaka vs. második 50% egy-trade összehasonlítás (régi „fő”
          forgatókönyv). A szekvenciális több trade részletei és TP/SL vonalak a fenti kis chartokon
          vannak; itt az aggregált több vágás statisztika.
        </p>
      </div>
      <p className="text-xs text-muted">
        Train: {wf.train_bar_count} gyertya · teszt: {wf.test_bar_count} · train medián (tiszta
        láb): {wf.median_move_pct_train != null ? `${wf.median_move_pct_train}%` : "—"} · TP és SL
        távolság: {wf.tp_move_pct != null ? `${wf.tp_move_pct}%` : "—"} (medián fele). Belépés:{" "}
        {wf.entry_price ?? "—"}
      </p>
      <div className="grid gap-2 sm:grid-cols-2 text-sm">
        <div>
          <span className="text-muted">Előrejelzett irány: </span>
          <span className="font-mono font-medium">{sideHu(wf.predicted_side)}</span>
          <span className="text-xs text-muted block mt-0.5">{reasonHu}</span>
        </div>
        <div>
          <span className="text-muted">Teszt nettó záró %: </span>
          <span className="font-mono">
            {wf.test_net_move_pct != null ? `${wf.test_net_move_pct}%` : "—"}
          </span>
          <span className="text-muted"> · tényleges oldal: </span>
          <span className="font-mono">{sideHu(wf.actual_test_side)}</span>
        </div>
        <div>
          <span className="text-muted">Iránytalálat (jó irányt tippeltünk-e): </span>
          {wf.direction_guess_correct === true ? (
            <span className="text-emerald-400 font-medium">igen</span>
          ) : wf.direction_guess_correct === false ? (
            <span className="text-rose-400 font-medium">nem</span>
          ) : (
            "—"
          )}
        </div>
        <div>
          <span className="text-muted">Előbb érintve: </span>
          <span className="font-medium">{touchLabel}</span>
          {wf.same_bar_ambiguous ? (
            <span className="text-xs text-amber-400 ml-1">(azon gyertyán mindkettő → SL előny)</span>
          ) : null}
        </div>
      </div>
      <div
        className={`rounded-md px-3 py-2 text-sm font-medium ${
          win
            ? "bg-emerald-500/15 text-emerald-200"
            : hitNone
              ? "bg-bg-card text-muted border border-border/50"
              : hitSl
                ? "bg-rose-500/15 text-rose-200"
                : "bg-bg-card text-muted"
        }`}
      >
        {win
          ? "Egy trade szimuláció (fő forgatókönyv): nyert — a TP érintődött volna előbb a checkpoint után."
          : hitSl
            ? "Egy trade szimuláció: vesztett — az SL érintődött volna előbb."
            : hitNone
              ? "Egy trade szimuláció: sem TP, sem SL nem érintődött a teszt ablakban."
              : "—"}
      </div>
      {wf.first_touch_time_ms != null ? (
        <p className="text-xs text-muted">
          Első érintés ideje: {new Date(wf.first_touch_time_ms).toLocaleString("hu-HU")}
        </p>
      ) : null}
      {aggBlock}
    </div>
  );
}
