"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { PnlSeriesBreakdown, PnlSeriesResponse } from "@/lib/api";
import { formatNumber } from "@/lib/utils";

function num(v: string | null | undefined): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

const SIDE_COLORS = ["#38bdf8", "#a78bfa", "#fbbf24", "#94a3b8"];

export function AnalyticsBreakdown({ pnl }: { pnl: PnlSeriesResponse }) {
  const breakdown = pnl.breakdown;
  const k = pnl.kpis;
  if (!breakdown) return null;

  const symbolData = breakdown.per_symbol.map((row) => ({
    symbol: row.symbol,
    pnl: num(row.realized_pnl_usdt),
    count: row.count,
  }));

  const winLossData = [
    { name: "Nyertes", value: k.wins, fill: "#4ade80" },
    { name: "Vesztes", value: k.losses, fill: "#f87171" },
  ].filter((d) => d.value > 0);

  const sideEntries = Object.entries(breakdown.by_side);

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
      <Card>
        <CardHeader>
          <CardTitle>PnL szimbólumonként</CardTitle>
        </CardHeader>
        <CardContent>
          {symbolData.length === 0 ? (
            <p className="text-muted text-sm">Nincs adat az ablakban.</p>
          ) : (
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={symbolData} layout="vertical" margin={{ left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis type="number" tick={{ fontSize: 10 }} stroke="#94a3b8" />
                  <YAxis
                    type="category"
                    dataKey="symbol"
                    width={72}
                    tick={{ fontSize: 10 }}
                    stroke="#94a3b8"
                  />
                  <Tooltip
                    contentStyle={{
                      background: "#1e293b",
                      border: "1px solid #334155",
                      fontSize: 12,
                    }}
                    formatter={(v: number, _n, item) => {
                      const payload = item?.payload as { count?: number };
                      return [
                        `${formatNumber(v, { decimals: 4, sign: true })} USDT · ${payload?.count ?? 0} poz.`,
                        "PnL",
                      ];
                    }}
                  />
                  <Bar dataKey="pnl" radius={[0, 2, 2, 0]}>
                    {symbolData.map((entry) => (
                      <Cell
                        key={entry.symbol}
                        fill={entry.pnl >= 0 ? "#4ade80" : "#f87171"}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Nyereség / veszteség</CardTitle>
        </CardHeader>
        <CardContent>
          {winLossData.length === 0 ? (
            <p className="text-muted text-sm">Nincs lezárt trade.</p>
          ) : (
            <div className="h-56 flex items-center justify-center">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={winLossData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={48}
                    outerRadius={72}
                    paddingAngle={2}
                  >
                    {winLossData.map((d) => (
                      <Cell key={d.name} fill={d.fill} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      background: "#1e293b",
                      border: "1px solid #334155",
                      fontSize: 12,
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
          <p className="text-center text-xs text-muted mt-2">
            {k.wins} nyertes · {k.losses} vesztes
            {k.win_rate_pct != null ? ` · ${k.win_rate_pct}% win rate` : ""}
          </p>
        </CardContent>
      </Card>

      {sideEntries.length > 0 && (
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Oldal szerinti bontás</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {sideEntries.map(([side, stats], i) => (
                <div
                  key={side}
                  className="rounded-lg border border-l-2 border-slate-700/60 bg-slate-900/40 p-3"
                  style={{ borderLeftColor: SIDE_COLORS[i % SIDE_COLORS.length] }}
                >
                  <p className="text-xs uppercase text-muted">{side}</p>
                  <p className="text-lg font-semibold text-slate-100">{stats.count}</p>
                  <p className="text-xs text-muted">
                    <span className="text-profit">{stats.wins} W</span>
                    {" · "}
                    <span className="text-loss">{stats.losses} L</span>
                  </p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <TopTradesTable title="Legjobb trade-ek" rows={breakdown.top_winners} positive />
      <TopTradesTable title="Legrosszabb trade-ek" rows={breakdown.top_losers} positive={false} />
    </div>
  );
}

function TopTradesTable({
  title,
  rows,
  positive,
}: {
  title: string;
  rows: PnlSeriesBreakdown["top_winners"];
  positive: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-muted text-sm">Nincs adat.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase text-muted border-b border-slate-700">
                  <th className="py-2 pr-2">Szimbólum</th>
                  <th className="py-2 pr-2">Oldal</th>
                  <th className="py-2 pr-2 text-right">PnL</th>
                  <th className="py-2 text-right">ROI</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => {
                  const pnlVal = num(row.realized_pnl_usdt);
                  return (
                    <tr key={`${row.symbol}-${i}`} className="border-b border-slate-800/80">
                      <td className="py-2 pr-2 font-medium">{row.symbol ?? "—"}</td>
                      <td className="py-2 pr-2 text-muted">{row.side ?? "—"}</td>
                      <td
                        className={`py-2 pr-2 text-right tabular-nums ${
                          positive ? "text-profit" : "text-loss"
                        }`}
                      >
                        {formatNumber(pnlVal, { decimals: 4, sign: true })}
                      </td>
                      <td className="py-2 text-right text-muted tabular-nums">
                        {row.roi_pct != null ? `${row.roi_pct}%` : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
