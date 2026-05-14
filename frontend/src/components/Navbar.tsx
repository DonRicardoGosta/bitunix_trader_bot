"use client";

import Link from "next/link";
import { Select } from "@/components/ui/input";
import {
  useRefreshInterval,
  type RefreshIntervalSec,
} from "@/contexts/RefreshIntervalContext";

const links = [
  { href: "/", label: "Dashboard" },
  { href: "/orders", label: "Rendelések" },
  { href: "/positions", label: "Pozíciók" },
  { href: "/strategies", label: "Stratégiák" },
  { href: "/coin-analyze", label: "Coin elemzés" },
  { href: "/calibration", label: "Kalibráció" },
  { href: "/events", label: "Eseménynapló" },
];

export function Navbar() {
  const { intervalSec, setIntervalSec, options } = useRefreshInterval();

  return (
    <header className="border-b border-border bg-bg-subtle/60 backdrop-blur sticky top-0 z-10">
      <div className="mx-auto max-w-7xl px-4 py-3 flex flex-wrap items-center justify-between gap-3">
        <Link href="/" className="flex items-center gap-2">
          <span className="text-xl font-bold text-accent">⟡ Bitunix Trader</span>
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <nav className="flex items-center gap-2 text-sm">
            {links.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="px-3 py-1.5 rounded-md text-slate-300 hover:bg-bg-card hover:text-slate-100 transition-colors"
              >
                {link.label}
              </Link>
            ))}
          </nav>
          <div className="flex items-center gap-2 border-l border-border/60 pl-3">
            <label htmlFor="ui-refresh-interval" className="text-xs text-muted whitespace-nowrap">
              Frissítés
            </label>
            <Select
              id="ui-refresh-interval"
              className="min-w-[5.5rem] text-sm"
              value={intervalSec}
              onChange={(e) => {
                const v = Number(e.target.value);
                if (options.includes(v as RefreshIntervalSec)) {
                  setIntervalSec(v as RefreshIntervalSec);
                }
              }}
            >
              {options.map((sec) => (
                <option key={sec} value={sec}>
                  {sec} mp
                </option>
              ))}
            </Select>
          </div>
        </div>
      </div>
    </header>
  );
}
