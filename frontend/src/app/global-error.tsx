"use client";

/**
 * Gyökér hiba — pl. ChunkLoadError dev módban Docker/HMR mellett.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const chunky =
    error.name === "ChunkLoadError" ||
    error.message.includes("Loading chunk");

  return (
    <html lang="hu" className="dark">
      <body className="min-h-screen bg-bg text-slate-100 flex items-center justify-center p-6">
        <div className="max-w-md space-y-4 text-center">
          <h1 className="text-xl font-semibold">Az oldal betöltése megszakadt</h1>
          <p className="text-sm text-muted">
            {chunky
              ? "A fejlesztői szerver valószínűleg újrafordított (Docker/HMR). Frissítsd az oldalt."
              : error.message || "Ismeretlen hiba."}
          </p>
          <div className="flex flex-wrap justify-center gap-2">
            <button
              type="button"
              className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white"
              onClick={() => window.location.reload()}
            >
              Teljes frissítés
            </button>
            <button
              type="button"
              className="rounded-md border border-border px-4 py-2 text-sm"
              onClick={() => reset()}
            >
              Újrapróbálás
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
