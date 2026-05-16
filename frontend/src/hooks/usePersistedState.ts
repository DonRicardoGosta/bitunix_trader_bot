"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * localStorage-ba mentett állapot (CSR only).
 * Az első render a defaultValue-t használja (SSR/hydration egyezés).
 */
export function usePersistedState(
  storageKey: string,
  defaultValue: number,
  isValid: (n: number) => boolean,
): [number, (value: number) => void] {
  const [value, setValue] = useState(defaultValue);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      if (raw == null) return;
      const n = Number(raw);
      if (isValid(n)) setValue(n);
    } catch {
      /* ignore */
    }
  }, [storageKey, isValid]);

  const setPersisted = useCallback(
    (next: number) => {
      if (!isValid(next)) return;
      setValue(next);
      try {
        localStorage.setItem(storageKey, String(next));
      } catch {
        /* ignore */
      }
    },
    [storageKey, isValid],
  );

  return [value, setPersisted];
}

/** localStorage-ba mentett string állapot (CSR only). */
function readStoredString<T extends string>(
  storageKey: string,
  defaultValue: T,
  isValid: (v: string) => v is T,
): T {
  if (typeof window === "undefined") return defaultValue;
  try {
    const raw = localStorage.getItem(storageKey);
    if (raw != null && isValid(raw)) return raw;
  } catch {
    /* ignore */
  }
  return defaultValue;
}

export function usePersistedStringState<T extends string>(
  storageKey: string,
  defaultValue: T,
  isValid: (v: string) => v is T,
): [T, (value: T) => void] {
  const [value, setValue] = useState<T>(() =>
    readStoredString(storageKey, defaultValue, isValid),
  );

  useEffect(() => {
    const stored = readStoredString(storageKey, defaultValue, isValid);
    if (stored !== value) setValue(stored);
  }, [storageKey, defaultValue, isValid, value]);

  const setPersisted = useCallback(
    (next: T) => {
      if (!isValid(next)) return;
      setValue(next);
      try {
        localStorage.setItem(storageKey, next);
      } catch {
        /* ignore */
      }
    },
    [storageKey, isValid],
  );

  return [value, setPersisted];
}
