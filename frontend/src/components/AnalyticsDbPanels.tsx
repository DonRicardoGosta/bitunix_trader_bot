"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AnalyticsOrdersWindow, AnalyticsStrategyWindow } from "@/lib/api";

export function AnalyticsDbPanels({
  orders,
  strategy,
}: {
  orders: AnalyticsOrdersWindow;
  strategy: AnalyticsStrategyWindow;
}) {
  const statusData = Object.entries(orders.by_status).map(([name, count]) => ({
    name,
    count,
  }));

  const strategyData = orders.by_strategy.slice(0, 8).map((row) => ({
    name: row.strategy,
    count: row.count,
  }));

  const runData = Object.entries(strategy.by_status).map(([name, count]) => ({
    name,
    count,
  }));

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Rendelések (DB)</CardTitle>
          <p className="text-xs text-muted">
            {orders.total} db az ablakban · státusz szerint
          </p>
        </CardHeader>
        <CardContent>
          {statusData.length === 0 ? (
            <p className="text-muted text-sm">Nincs rendelés.</p>
          ) : (
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={statusData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} stroke="#94a3b8" />
                  <YAxis tick={{ fontSize: 10 }} stroke="#94a3b8" allowDecimals={false} />
                  <Tooltip
                    contentStyle={{
                      background: "#1e293b",
                      border: "1px solid #334155",
                      fontSize: 12,
                    }}
                  />
                  <Bar dataKey="count" fill="#38bdf8" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Stratégia futások</CardTitle>
          <p className="text-xs text-muted">DB strategy_runs státusz</p>
        </CardHeader>
        <CardContent>
          {runData.length === 0 ? (
            <p className="text-muted text-sm">Nincs futás az ablakban.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {runData.map((row) => (
                <li
                  key={row.name}
                  className="flex justify-between border-b border-slate-800/80 py-1"
                >
                  <span className="text-muted">{row.name}</span>
                  <span className="font-medium tabular-nums">{row.count}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {strategyData.length > 0 && (
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Rendelések stratégiánként</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-52">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={strategyData} layout="vertical" margin={{ left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis type="number" tick={{ fontSize: 10 }} stroke="#94a3b8" allowDecimals={false} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={120}
                    tick={{ fontSize: 9 }}
                    stroke="#94a3b8"
                  />
                  <Tooltip
                    contentStyle={{
                      background: "#1e293b",
                      border: "1px solid #334155",
                      fontSize: 12,
                    }}
                  />
                  <Bar dataKey="count" fill="#a78bfa" radius={[0, 2, 2, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
