import * as React from "react";
import { cn } from "@/lib/utils";

export interface StatCardProps {
  label: string;
  value: React.ReactNode;
  /** Pl. "USDT", "%" */
  unit?: string;
  /** Másodlagos magyarázat (kis betű) */
  hint?: React.ReactNode;
  /** "positive"/"negative"/"neutral" — színezés a fő értéken */
  tone?: "positive" | "negative" | "neutral" | "accent";
  /** Bal oldali ikon vagy badge */
  icon?: React.ReactNode;
  className?: string;
  /** Loader állapot */
  loading?: boolean;
  /** Hosszú számok tördelése (ne vágja le truncate) */
  wrapValue?: boolean;
}

const toneClass: Record<NonNullable<StatCardProps["tone"]>, string> = {
  positive: "text-profit",
  negative: "text-loss",
  neutral: "text-slate-100",
  accent: "text-accent",
};

export function StatCard({
  label,
  value,
  unit,
  hint,
  tone = "neutral",
  icon,
  className,
  loading,
  wrapValue = false,
}: StatCardProps) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-bg-card p-4 flex items-start gap-3",
        className,
      )}
    >
      {icon ? (
        <div className="shrink-0 mt-1 text-accent" aria-hidden>
          {icon}
        </div>
      ) : null}
      <div className="min-w-0 flex-1">
        <div className="text-xs uppercase tracking-wide text-muted">
          {label}
        </div>
        <div
          className={cn(
            "mt-1 flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 font-semibold tabular-nums",
            wrapValue ? "text-lg sm:text-xl" : "text-2xl",
            toneClass[tone],
          )}
        >
          {loading ? (
            <span className="inline-block h-6 w-20 rounded bg-bg-subtle animate-pulse" />
          ) : (
            <span className={cn("num", wrapValue ? "break-all" : "truncate")}>
              {value}
            </span>
          )}
          {unit ? (
            <span className="text-xs font-normal text-muted shrink-0">{unit}</span>
          ) : null}
        </div>
        {hint ? (
          <div className="text-xs text-muted mt-1 leading-snug">{hint}</div>
        ) : null}
      </div>
    </div>
  );
}
