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
import { api, type CleanLegRow, type CoinAnalyzeResult, type MarketSymbolRow } from "@/lib/api";

const WF_REASON_HU: Record<string, string> = {
  clean_legs_up_majority: "Tiszta lábak: több felfelé szakasz",
  clean_legs_down_majority: "Tiszta lábak: több lefelé szakasz",
  clean_legs_tie_positive_net_close: "Döntetlen lábak, nettó záró emelkedett",
  clean_legs_tie_negative_net_close: "Döntetlen lábak, nettó záró csökkent",
  clean_legs_tie_flat_close: "Döntetlen lábak, sík záró → long alapértelmezés",
};

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

type WfLinePoint = { t: number; y: number };

function useWalkForwardChartOverlay(result: CoinAnalyzeResult | null) {
  return useMemo(() => {
    const wf = result?.walk_forward;
    if (!wf?.enabled) return null;
    if (
      wf.checkpoint_time_ms == null ||
      wf.test_start_time_ms == null ||
      wf.test_end_time_ms == null ||
      wf.train_start_time_ms == null ||
      wf.train_end_time_ms == null ||
      wf.entry_price == null ||
      wf.tp_price == null ||
      wf.sl_price == null ||
      wf.test_start_close == null ||
      wf.test_end_close == null
    ) {
      return null;
    }
    const cp = wf.checkpoint_time_ms;
    const ts = wf.test_start_time_ms;
    const te = wf.test_end_time_ms;
    const entry = Number(wf.entry_price);
    const tp = Number(wf.tp_price);
    const sl = Number(wf.sl_price);
    const tsc = Number(wf.test_start_close);
    const tec = Number(wf.test_end_close);
    return {
      trainStart: wf.train_start_time_ms,
      trainEnd: wf.train_end_time_ms,
      testStart: ts,
      testEnd: te,
      entryLine: [
        { t: cp, y: entry },
        { t: te, y: entry },
      ] satisfies WfLinePoint[],
      tpLine: [
        { t: ts, y: tp },
        { t: te, y: tp },
      ] satisfies WfLinePoint[],
      slLine: [
        { t: ts, y: sl },
        { t: te, y: sl },
      ] satisfies WfLinePoint[],
      actualLine: [
        { t: ts, y: tsc },
        { t: te, y: tec },
      ] satisfies WfLinePoint[],
      aimLine: [
        { t: cp, y: entry },
        { t: te, y: tp },
      ] satisfies WfLinePoint[],
    };
  }, [result]);
}

export default function CoinAnalyzePage() {
  const [symbols, setSymbols] = useState<MarketSymbolRow[] | null>(null);
  const [symbol, setSymbol] = useState("");
  const [lookbackMin, setLookbackMin] = useState(1440);
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

  const wfOv = useWalkForwardChartOverlay(result);

  const chartData: ChartPoint[] = useMemo(() => {
    if (!result?.candles.length) return [];
    return result.candles.map((k) => ({
      t: k.time_ms,
      c: Number(k.close),
      hi: Number(k.high),
      lo: Number(k.low),
    }));
  }, [result]);

  const runAnalyze = useCallback(async () => {
    if (!symbol.trim()) return;
    setLoadingRun(true);
    setError(null);
    try {
      const res = await api.coinAnalyze({
        symbol: symbol.trim().toUpperCase(),
        lookback_minutes: lookbackMin,
      });
      setResult(res);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : "Elemzés sikertelen");
    } finally {
      setLoadingRun(false);
    }
  }, [symbol, lookbackMin]);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Coin elemzés</CardTitle>
          <p className="text-sm text-muted">
            A teljes lookbackon swing / tiszta láb elemzés látszik. A charton külön jelöljük:{" "}
            <span className="font-medium text-foreground">kék zóna</span> = train (első fél időben,
            ebből medián + irány), <span className="font-medium text-foreground">borostyán</span> =
            teszt (második fél). A sárga függőleges a checkpoint; a teszt szakaszon{" "}
            <span className="font-medium text-foreground">sárga vízszintes</span> belépés,{" "}
            <span className="font-medium text-emerald-300">zöld</span> TP,{" "}
            <span className="font-medium text-rose-300">piros</span> SL.{" "}
            <span className="font-medium text-orange-300">Narancs</span> = tényleges záró út a
            teszten; <span className="font-medium text-violet-300">lila</span> = a fogadás felé
            mutató cél (checkpoint → TP szint a teszt végén).
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
                Kért lookback: {result.lookback_minutes_requested} perc · choppiness küszöb ≤{" "}
                {result.choppiness_max} · tiszta lábak: {result.clean_leg_count} / összes láb:{" "}
                {result.all_leg_count}
              </p>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-3 mb-4">
                <Stat label="Medián mozgás (tiszta láb)" value={result.median_move_pct} suffix="%" />
                <Stat label="Átlag mozgás" value={result.mean_move_pct} suffix="%" />
                <Stat label="Max. leverage" value={String(result.max_leverage)} suffix="×" />
              </div>
              {wfOv ? (
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted mb-2 border border-border/40 rounded-md px-2 py-1.5 bg-bg-subtle/80">
                  <span>
                    <span className="inline-block w-2.5 h-2.5 rounded-sm bg-sky-500/40 mr-1 align-middle" />
                    Train zóna
                  </span>
                  <span>
                    <span className="inline-block w-2.5 h-2.5 rounded-sm bg-amber-500/35 mr-1 align-middle" />
                    Teszt zóna
                  </span>
                  <span className="text-amber-200">━</span> Belépés
                  <span className="text-emerald-400">━</span> TP
                  <span className="text-rose-400">━</span> SL
                  <span className="text-orange-400">━</span> Tényleges záró
                  <span className="text-violet-300">┅</span> Cél (TP irány)
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
                    {wfOv ? (
                      <>
                        <ReferenceArea
                          x1={wfOv.trainStart}
                          x2={wfOv.trainEnd}
                          fill="rgba(59,130,246,0.10)"
                          stroke="none"
                          ifOverflow="visible"
                        />
                        <ReferenceArea
                          x1={wfOv.testStart}
                          x2={wfOv.testEnd}
                          fill="rgba(245,158,11,0.09)"
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
                        fill={leg.direction === "up" ? "rgba(34,197,94,0.14)" : "rgba(248,113,113,0.14)"}
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
                    {wfOv ? (
                      <>
                        <Line
                          name="Belépés (teszt)"
                          data={wfOv.entryLine}
                          dataKey="y"
                          type="linear"
                          stroke="#facc15"
                          strokeWidth={1.5}
                          strokeDasharray="6 4"
                          dot={false}
                          isAnimationActive={false}
                        />
                        <Line
                          name="TP szint"
                          data={wfOv.tpLine}
                          dataKey="y"
                          type="linear"
                          stroke="#4ade80"
                          strokeWidth={1.5}
                          strokeDasharray="5 4"
                          dot={false}
                          isAnimationActive={false}
                        />
                        <Line
                          name="SL szint"
                          data={wfOv.slLine}
                          dataKey="y"
                          type="linear"
                          stroke="#fb7185"
                          strokeWidth={1.5}
                          strokeDasharray="5 4"
                          dot={false}
                          isAnimationActive={false}
                        />
                        <Line
                          name="Tényleges záró (teszt)"
                          data={wfOv.actualLine}
                          dataKey="y"
                          type="linear"
                          stroke="#fb923c"
                          strokeWidth={2.2}
                          dot={false}
                          isAnimationActive={false}
                        />
                        <Line
                          name="Fogadás → TP cél"
                          data={wfOv.aimLine}
                          dataKey="y"
                          type="linear"
                          stroke="#c4b5fd"
                          strokeWidth={2}
                          strokeDasharray="3 5"
                          dot={false}
                          isAnimationActive={false}
                        />
                      </>
                    ) : null}
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
                A halvány zöld/piros sávok a teljes ablak „tiszta” swing lábai (choppiness szűrés). A
                kék és borostyán háttér a walk-forward train / teszt időszaka. A narancs vonal a teszt
                első és utolsó zárója között mutatja, merre ment a piac; a lila a checkpointtól a TP
                szint felé mutató egyenes (merre fogadtunk). A sárga függőleges a checkpoint (train
                utolsó gyertya).
              </p>
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
          A charton a kék / borostyán sáv a train vs teszt; a narancs vonal a teszt első és utolsó
          zárója (merre ment a piac); a lila a checkpointtól a TP szintig (merre fogadtunk). A sárga
          vízszintes a belépési ár a teszt szakaszon, zöld/piros a TP/SL szintek.
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
