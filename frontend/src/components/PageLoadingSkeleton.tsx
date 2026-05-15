/** Közös skeleton menüváltás / Next.js `loading.tsx` alatt. */
export function PageLoadingSkeleton() {
  return (
    <div
      className="space-y-6 animate-pulse"
      role="status"
      aria-live="polite"
      aria-label="Oldal betöltése"
    >
      <div className="h-8 w-48 rounded-md bg-bg-card/80" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-24 rounded-lg border border-border/60 bg-bg-card/50" />
        ))}
      </div>
      <div className="h-64 rounded-lg border border-border/60 bg-bg-card/40" />
      <p className="text-sm text-muted">Betöltés…</p>
    </div>
  );
}
