"use client";

import { useNavigationLoading } from "@/contexts/NavigationLoadingContext";
import { cn } from "@/lib/utils";

/** Vékony progress sáv a fejléc alatt menüváltáskor. */
export function RouteLoadingBar() {
  const { isNavigating } = useNavigationLoading();

  return (
    <div
      role="progressbar"
      aria-hidden={!isNavigating}
      aria-busy={isNavigating}
      aria-label="Oldal betöltése"
      className={cn(
        "pointer-events-none absolute inset-x-0 bottom-0 h-0.5 overflow-hidden bg-accent/15",
        "transition-opacity duration-150",
        isNavigating ? "opacity-100" : "opacity-0",
      )}
    >
      <span
        className={cn(
          "block h-full w-1/3 bg-accent shadow-[0_0_12px_rgba(34,211,238,0.55)]",
          isNavigating ? "animate-route-loading-bar" : "",
        )}
      />
    </div>
  );
}
