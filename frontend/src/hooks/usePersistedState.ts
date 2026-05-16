"use client";

import { useCallback, useEffect, useRef, useState } from "react";

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
  const isValidRef = useRef(isValid);
  isValidRef.current = isValid;

  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      if (raw == null) return;
      const n = Number(raw);
      if (isValidRef.current(n)) setValue(n);
    } catch {
      /* ignore */
    }
  }, [storageKey]);

  const setPersisted = useCallback(
    (next: number) => {
      if (!isValidRef.current(next)) return;
      setValue(next);
      try {
        localStorage.setItem(storageKey, String(next));
      } catch {
        /* ignore */
      }
    },
    [storageKey],
  );

  return [value, setPersisted];
}

/** localStorage-ba mentett string állapot (CSR only). */
export function usePersistedStringState<T extends string>(
  storageKey: string,
  defaultValue: T,
  isValid: (v: string) => v is T,
): [T, (value: T) => void] {
  const [value, setValue] = useState<T>(defaultValue);
  const isValidRef = useRef(isValid);
  isValidRef.current = isValid;

  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      if (raw == null) return;
      if (isValidRef.current(raw)) setValue(raw as T);
    } catch {
      /* ignore */
    }
  }, [storageKey]);

  const setPersisted = useCallback(
    (next: T) => {
      if (!isValidRef.current(next)) return;
      setValue(next);
      try {
        localStorage.setItem(storageKey, next);
      } catch {
        /* ignore */
      }
    },
    [storageKey],
  );

  return [value, setPersisted];
}
