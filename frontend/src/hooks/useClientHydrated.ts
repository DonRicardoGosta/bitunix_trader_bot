"use client";

import { useEffect, useState } from "react";

/** true az első kliens mount után (hydration után). */
export function useClientHydrated(): boolean {
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    setHydrated(true);
  }, []);
  return hydrated;
}
