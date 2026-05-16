"use client";

import { cn } from "@/lib/utils";

/** Diszkrét háttér-frissítés jelzés – nem sötétíti az egész oldalt. */
export function RefreshIndicator({
  active,
  className,
}: {
  active: boolean;
  className?: string;
}) {
  if (!active) return null;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-[10px] uppercase tracking-wide text-accent/90",
        className,
      )}
      aria-live="polite"
    >
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-accent animate-pulse" />
      frissítés
    </span>
  );
}
