"use client";

import { useEffect } from "react";

const RELOAD_KEY = "bitunix_chunk_reload";

function isChunkLoadFailure(reason: unknown): boolean {
  if (reason == null) return false;
  const name =
    typeof reason === "object" && reason !== null && "name" in reason
      ? String((reason as { name?: string }).name)
      : "";
  const message =
    typeof reason === "string"
      ? reason
      : typeof reason === "object" &&
          reason !== null &&
          "message" in reason
        ? String((reason as { message?: string }).message)
        : String(reason);
  return (
    name === "ChunkLoadError" ||
    message.includes("ChunkLoadError") ||
    message.includes("Loading chunk")
  );
}

/**
 * Dev / Docker HMR: ha a szerver újrafordít közben chunkot kérsz, egy automatikus
 * reload gyakran helyreállítja az oldalt (ChunkLoadError / ERR_CONNECTION_RESET).
 */
export function ChunkLoadRecovery() {
  useEffect(() => {
    const tryReload = () => {
      const n = Number(sessionStorage.getItem(RELOAD_KEY) || "0");
      if (n >= 2) return;
      sessionStorage.setItem(RELOAD_KEY, String(n + 1));
      window.location.reload();
    };

    const onError = (event: ErrorEvent) => {
      if (isChunkLoadFailure(event.error) || isChunkLoadFailure(event.message)) {
        tryReload();
      }
    };

    const onRejection = (event: PromiseRejectionEvent) => {
      if (isChunkLoadFailure(event.reason)) {
        tryReload();
      }
    };

    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    sessionStorage.removeItem(RELOAD_KEY);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }, []);

  return null;
}
