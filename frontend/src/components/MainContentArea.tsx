"use client";

import type { ReactNode } from "react";
import { useNavigationLoading } from "@/contexts/NavigationLoadingContext";
import { PageLoadingSkeleton } from "@/components/PageLoadingSkeleton";
import { cn } from "@/lib/utils";

export function MainContentArea({ children }: { children: ReactNode }) {
  const { isNavigating } = useNavigationLoading();

  return (
    <main className="relative mx-auto max-w-[90rem] px-4 py-6">
      {isNavigating ? (
        <div className="absolute inset-0 z-[1] px-4 py-6 pointer-events-none">
          <PageLoadingSkeleton />
        </div>
      ) : null}
      <div
        className={cn(
          "transition-opacity duration-150",
          isNavigating ? "opacity-40 pointer-events-none select-none" : "opacity-100",
        )}
        aria-hidden={isNavigating}
      >
        {children}
      </div>
    </main>
  );
}
