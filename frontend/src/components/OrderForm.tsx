"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/input";
import { api, type PlaceOrderResult } from "@/lib/api";

interface State {
  symbol: string;
  side: "BUY" | "SELL";
  orderType: "MARKET" | "LIMIT";
  quantity: string;
  price: string;
  leverage: string;
  reduceOnly: boolean;
}

const INITIAL: State = {
  symbol: "BTCUSDT",
  side: "BUY",
  orderType: "MARKET",
  quantity: "0.001",
  price: "",
  leverage: "5",
  reduceOnly: false,
};

export function OrderForm() {
  const [state, setState] = useState<State>(INITIAL);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PlaceOrderResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  function update<K extends keyof State>(key: K, value: State[K]) {
    setState((prev) => ({ ...prev, [key]: value }));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.placeOrder({
        symbol: state.symbol.trim().toUpperCase(),
        side: state.side,
        orderType: state.orderType,
        quantity: state.quantity,
        price:
          state.orderType === "LIMIT" && state.price ? state.price : undefined,
        leverage: Number(state.leverage),
        reduceOnly: state.reduceOnly,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ismeretlen hiba");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" data-testid="order-form">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="symbol">Szimbólum</Label>
          <Input
            id="symbol"
            value={state.symbol}
            onChange={(e) => update("symbol", e.target.value)}
            required
          />
        </div>
        <div>
          <Label htmlFor="side">Irány</Label>
          <Select
            id="side"
            value={state.side}
            onChange={(e) => update("side", e.target.value as "BUY" | "SELL")}
          >
            <option value="BUY">LONG / BUY</option>
            <option value="SELL">SHORT / SELL</option>
          </Select>
        </div>
        <div>
          <Label htmlFor="type">Típus</Label>
          <Select
            id="type"
            value={state.orderType}
            onChange={(e) =>
              update("orderType", e.target.value as "MARKET" | "LIMIT")
            }
          >
            <option value="MARKET">MARKET</option>
            <option value="LIMIT">LIMIT</option>
          </Select>
        </div>
        <div>
          <Label htmlFor="leverage">Tőkeáttétel</Label>
          <Input
            id="leverage"
            type="number"
            min={1}
            max={125}
            value={state.leverage}
            onChange={(e) => update("leverage", e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="qty">Mennyiség</Label>
          <Input
            id="qty"
            type="number"
            step="any"
            value={state.quantity}
            onChange={(e) => update("quantity", e.target.value)}
            required
          />
        </div>
        <div>
          <Label htmlFor="price">Ár (csak LIMIT)</Label>
          <Input
            id="price"
            type="number"
            step="any"
            value={state.price}
            onChange={(e) => update("price", e.target.value)}
            disabled={state.orderType === "MARKET"}
          />
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={state.reduceOnly}
          onChange={(e) => update("reduceOnly", e.target.checked)}
          className="accent-accent"
        />
        <span>reduceOnly (csak pozíció csökkentés)</span>
      </label>

      <Button
        type="submit"
        disabled={busy}
        variant={state.side === "BUY" ? "success" : "danger"}
        className="w-full"
      >
        {busy
          ? "Küldés…"
          : state.side === "BUY"
            ? `LONG ${state.symbol}`
            : `SHORT ${state.symbol}`}
      </Button>

      {error && (
        <div className="rounded-md border border-loss/50 bg-loss/10 p-3 text-sm text-red-300">
          Hiba: {error}
        </div>
      )}
      {result && (
        <div className="rounded-md border border-border bg-bg-subtle p-3 text-sm space-y-1">
          <div className="flex justify-between">
            <span className="text-muted">client_order_id</span>
            <span className="num">{result.client_order_id}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted">Státusz</span>
            <span>{result.status}</span>
          </div>
          {result.dry_run && (
            <div className="text-yellow-400 text-xs">
              ⚠ DRY-RUN: a backend dry-run módban fut (BITUNIX_LIVE_TRADING=false)
            </div>
          )}
        </div>
      )}
    </form>
  );
}
