"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Select } from "@/components/ui/input";
import {
  useRefreshInterval,
  type RefreshIntervalSec,
} from "@/contexts/RefreshIntervalContext";
import { useLivePushConnected } from "@/contexts/LiveUpdatesContext";
import { useNavigationLoading } from "@/contexts/NavigationLoadingContext";
import { RouteLoadingBar } from "@/components/RouteLoadingBar";
import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "Dashboard" },
  { href: "/analytics", label: "Analytics" },
  { href: "/orders", label: "Rendelések" },
  { href: "/positions", label: "Pozíciók" },
  { href: "/strategies", label: "Stratégiák" },
  { href: "/settings", label: "Vezérlőpult" },
  { href: "/coin-analyze", label: "Coin elemzés" },
  { href: "/calibration", label: "Kalibráció" },
  { href: "/events", label: "Eseménynapló" },
];

export function Navbar() {
  const pathname = usePathname();
  const { intervalSec, setIntervalSec, options } = useRefreshInterval();
  const pushConnected = useLivePushConnected();
  const { isNavigating, pendingPath } = useNavigationLoading();

  return (
    <header className="relative border-b border-border bg-bg-subtle/60 backdrop-blur sticky top-0 z-10">
      <RouteLoadingBar />
      <div className="mx-auto max-w-[90rem] px-4 py-3 flex flex-wrap items-center justify-between gap-3">
        <Link href="/" className="flex items-center gap-2">
          <span className="text-xl font-bold text-accent">⟡ Bitunix Trader</span>
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <nav className="flex items-center gap-2 text-sm">
            {links.map((link) => {
              const active =
                link.href === "/"
                  ? pathname === "/"
                  : pathname === link.href || pathname.startsWith(`${link.href}/`);
              const pending = isNavigating && pendingPath === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={cn(
                    "px-3 py-1.5 rounded-md transition-colors",
                    active && !pending
                      ? "bg-bg-card text-slate-100"
                      : "text-slate-300 hover:bg-bg-card hover:text-slate-100",
                    pending && "bg-bg-card/60 text-accent animate-pulse",
                  )}
                  aria-current={active && !pending ? "page" : undefined}
                >
                  {pending ? `${link.label}…` : link.label}
                </Link>
              );
            })}
          </nav>
          {!pushConnected ? (
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
          ) : (
            <div
              className="border-l border-border/60 pl-3 text-xs text-muted whitespace-nowrap"
              title="WebSocket élő invalidáció; polling kikapcsolva."
            >
              Élő frissítés
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
