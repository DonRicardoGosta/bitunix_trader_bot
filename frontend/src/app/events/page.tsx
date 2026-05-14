"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { buildCsv, downloadCsvFile } from "@/lib/csvExport";
import { api, type AuditEventRow } from "@/lib/api";
import { useRefreshInterval } from "@/contexts/RefreshIntervalContext";
import { useLiveEpoch, useLivePushConnected } from "@/contexts/LiveUpdatesContext";

export default function EventsPage() {
  const { refreshIntervalMs } = useRefreshInterval();
  const pushConnected = useLivePushConnected();
  const eventsEpoch = useLiveEpoch("events");
  const [rows, setRows] = useState<AuditEventRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [level, setLevel] = useState<string>("");
  const [prefix, setPrefix] = useState<string>("");
  const [strategy, setStrategy] = useState<string>("");

  const load = useCallback(async () => {
    try {
      const r = await api.events({
        level: level || undefined,
        event_prefix: prefix || undefined,
        strategy_name: strategy || undefined,
        limit: 200,
      });
      setRows(r);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Hiba a betöltéskor");
    }
  }, [level, prefix, strategy]);

  const exportCsv = useCallback(() => {
    if (!rows?.length) return;
    const headers = [
      "id",
      "created_at",
      "level",
      "event",
      "strategy_name",
      "message",
      "payload_json",
    ];
    const dataRows = rows.map((e) => [
      String(e.id),
      e.created_at ?? "",
      e.level ?? "",
      e.event,
      e.strategy_name ?? "",
      e.message ?? "",
      e.payload ? JSON.stringify(e.payload) : "",
    ]);
    const csv = buildCsv(headers, dataRows);
    downloadCsvFile(
      `audit-events-${new Date().toISOString().slice(0, 19).replace(/:/g, "-")}.csv`,
      csv,
    );
  }, [rows]);

  useEffect(() => {
    void load();
    if (pushConnected) {
      return undefined;
    }
    const id = setInterval(load, refreshIntervalMs);
    return () => clearInterval(id);
  }, [load, refreshIntervalMs, pushConnected, eventsEpoch]);

  return (
    <Card>
      <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <CardTitle>Eseménynapló</CardTitle>
          <span className="text-xs text-muted">
            minden audit esemény DB-be mentve – nincs külön log fájl
          </span>
        </div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          className="shrink-0"
          disabled={!rows?.length}
          onClick={() => exportCsv()}
        >
          CSV export
        </Button>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 mb-4">
          <div>
            <Label htmlFor="level">Szint</Label>
            <Select
              id="level"
              value={level}
              onChange={(e) => setLevel(e.target.value)}
            >
              <option value="">Mind</option>
              <option value="DEBUG">DEBUG</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
            </Select>
          </div>
          <div>
            <Label htmlFor="prefix">Esemény előtag</Label>
            <Input
              id="prefix"
              placeholder="pl. strategy.top_movers"
              value={prefix}
              onChange={(e) => setPrefix(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="strategy">Stratégia</Label>
            <Input
              id="strategy"
              placeholder="pl. top_movers"
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
            />
          </div>
          <div className="flex items-end">
            <Button variant="secondary" onClick={() => load()} className="w-full">
              Frissítés
            </Button>
          </div>
        </div>

        {error && <p className="text-loss text-sm mb-2">{error}</p>}
        {!rows && <p className="text-muted text-sm">Betöltés…</p>}
        {rows && rows.length === 0 && (
          <p className="text-muted text-sm">Nincs esemény a szűrőre.</p>
        )}
        {rows && rows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs uppercase text-muted border-b border-border">
                <tr>
                  <th className="text-left py-2 pr-3">Idő</th>
                  <th className="text-left py-2 pr-3">Szint</th>
                  <th className="text-left py-2 pr-3">Esemény</th>
                  <th className="text-left py-2 pr-3">Stratégia</th>
                  <th className="text-left py-2 pr-3">Üzenet</th>
                  <th className="text-left py-2 pr-3">Részlet</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((e) => (
                  <tr key={e.id} className="border-b border-border/50 align-top">
                    <td className="py-2 pr-3 text-muted num whitespace-nowrap">
                      {e.created_at
                        ? new Date(e.created_at).toLocaleString("hu-HU")
                        : "—"}
                    </td>
                    <td className="py-2 pr-3">
                      <LevelBadge level={e.level} />
                    </td>
                    <td className="py-2 pr-3 font-mono text-xs">{e.event}</td>
                    <td className="py-2 pr-3 text-muted">
                      {e.strategy_name ?? "—"}
                    </td>
                    <td className="py-2 pr-3 max-w-md whitespace-pre-wrap break-words">
                      {e.message ?? "—"}
                    </td>
                    <td className="py-2 pr-3 max-w-lg">
                      <EventPayloadDetail payload={e.payload} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function EventPayloadDetail({
  payload,
}: {
  payload: Record<string, unknown> | null;
}) {
  if (!payload || Object.keys(payload).length === 0) {
    return <span className="text-muted text-xs">—</span>;
  }
  const pretty = JSON.stringify(payload, null, 2);
  return (
    <details className="text-xs">
      <summary className="cursor-pointer text-muted hover:text-fg">
        Payload (kattints)
      </summary>
      <pre className="mt-2 max-h-56 overflow-auto rounded-md border border-border bg-bg-subtle p-2 font-mono text-[11px] leading-snug text-fg">
        {pretty}
      </pre>
    </details>
  );
}

function LevelBadge({ level }: { level: string | null }) {
  if (!level) return <span className="text-muted">—</span>;
  const color: Record<string, string> = {
    DEBUG: "text-muted border-muted/40",
    INFO: "text-accent border-accent/40",
    WARNING: "text-yellow-400 border-yellow-400/40",
    ERROR: "text-loss border-loss/40",
  };
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-xs border bg-bg-subtle ${color[level] ?? "text-muted border-muted/40"}`}
    >
      {level}
    </span>
  );
}
