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
