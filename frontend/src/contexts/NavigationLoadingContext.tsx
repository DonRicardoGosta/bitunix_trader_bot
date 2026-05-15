"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { usePathname } from "next/navigation";

const MIN_VISIBLE_MS = 200;

type NavigationLoadingContextValue = {
  isNavigating: boolean;
  /** Cél útvonal (menüpont jelöléshez), vagy null. */
  pendingPath: string | null;
  /** Kézi indítás (pl. programozott router.push). */
  startNavigation: (targetPath?: string) => void;
};

const NavigationLoadingContext = createContext<NavigationLoadingContextValue | null>(
  null,
);

function isSameRoute(href: string, pathname: string): boolean {
  try {
    const url = new URL(href, window.location.origin);
    const current =
      pathname + (window.location.search ? window.location.search : "");
    const next = url.pathname + (url.search ? url.search : "");
    return next === current;
  } catch {
    return true;
  }
}

function anchorFromEventTarget(target: EventTarget | null): HTMLAnchorElement | null {
  if (!(target instanceof Element)) return null;
  const anchor = target.closest("a");
  if (!anchor) return null;
  if (anchor.target === "_blank" || anchor.hasAttribute("download")) return null;
  const href = anchor.getAttribute("href");
  if (!href || href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("tel:")) {
    return null;
  }
  try {
    const url = new URL(anchor.href, window.location.origin);
    if (url.origin !== window.location.origin) return null;
  } catch {
    return null;
  }
  return anchor;
}

export function NavigationLoadingProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [isNavigating, setIsNavigating] = useState(false);
  const [pendingPath, setPendingPath] = useState<string | null>(null);
  const startedAtRef = useRef<number | null>(null);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearHideTimer = useCallback(() => {
    if (hideTimerRef.current != null) {
      clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
  }, []);

  const startNavigation = useCallback(
    (targetPath?: string) => {
      clearHideTimer();
      startedAtRef.current = Date.now();
      setPendingPath(targetPath ?? null);
      setIsNavigating(true);
    },
    [clearHideTimer],
  );

  const finishNavigation = useCallback(() => {
    clearHideTimer();
    const started = startedAtRef.current;
    if (started == null) {
      setIsNavigating(false);
      return;
    }
    const elapsed = Date.now() - started;
    const wait = Math.max(0, MIN_VISIBLE_MS - elapsed);
    hideTimerRef.current = setTimeout(() => {
      startedAtRef.current = null;
      setPendingPath(null);
      setIsNavigating(false);
      hideTimerRef.current = null;
    }, wait);
  }, [clearHideTimer]);

  useEffect(() => {
    finishNavigation();
  }, [pathname, finishNavigation]);

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented) return;
      if (event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const anchor = anchorFromEventTarget(event.target);
      if (!anchor) return;
      if (!isSameRoute(anchor.href, pathname)) {
        try {
          const nextPath = new URL(anchor.href, window.location.origin).pathname;
          startNavigation(nextPath);
        } catch {
          startNavigation();
        }
      }
    };

    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [pathname, startNavigation]);

  useEffect(() => () => clearHideTimer(), [clearHideTimer]);

  return (
    <NavigationLoadingContext.Provider
      value={{ isNavigating, pendingPath, startNavigation }}
    >
      {children}
    </NavigationLoadingContext.Provider>
  );
}

export function useNavigationLoading(): NavigationLoadingContextValue {
  const ctx = useContext(NavigationLoadingContext);
  if (!ctx) {
    throw new Error("useNavigationLoading must be used within NavigationLoadingProvider");
  }
  return ctx;
}
