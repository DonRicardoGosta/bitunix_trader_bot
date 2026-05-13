"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface PaginationProps {
  page: number;
  pageSize: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  className?: string;
  /**
   * Ha igaz, akkor a "ebből X – Y" infó a totalItems alapján a tényleges
   * pozíciót mutatja; ha nem ismert a total (pl. szerver-paginált), állítsd
   * false-ra: ekkor csak a navigáció jelenik meg.
   */
  showTotals?: boolean;
}

export function totalPages(totalItems: number, pageSize: number): number {
  if (pageSize <= 0) return 1;
  return Math.max(1, Math.ceil(totalItems / pageSize));
}

/** Indexed slice + helper a sorok kivágásához (1-alapú page). */
export function pageSlice<T>(items: T[], page: number, pageSize: number): T[] {
  const start = Math.max(0, (page - 1) * pageSize);
  return items.slice(start, start + pageSize);
}

export function Pagination({
  page,
  pageSize,
  totalItems,
  onPageChange,
  className,
  showTotals = true,
}: PaginationProps) {
  const pages = totalPages(totalItems, pageSize);
  const clampedPage = Math.min(Math.max(1, page), pages);
  const first = totalItems === 0 ? 0 : (clampedPage - 1) * pageSize + 1;
  const last = Math.min(totalItems, clampedPage * pageSize);
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-2 text-xs text-muted",
        className,
      )}
    >
      {showTotals && (
        <div>
          {totalItems === 0 ? (
            "0 elem"
          ) : (
            <>
              <span className="num">{first}</span>–<span className="num">{last}</span>{" "}
              / <span className="num">{totalItems}</span>
            </>
          )}
        </div>
      )}
      <div className="flex items-center gap-1">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          aria-label="Első oldal"
          disabled={clampedPage <= 1}
          onClick={() => onPageChange(1)}
        >
          «
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          aria-label="Előző oldal"
          disabled={clampedPage <= 1}
          onClick={() => onPageChange(clampedPage - 1)}
        >
          ‹
        </Button>
        <span className="px-2">
          <span className="num">{clampedPage}</span> / <span className="num">{pages}</span>
        </span>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          aria-label="Következő oldal"
          disabled={clampedPage >= pages}
          onClick={() => onPageChange(clampedPage + 1)}
        >
          ›
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          aria-label="Utolsó oldal"
          disabled={clampedPage >= pages}
          onClick={() => onPageChange(pages)}
        >
          »
        </Button>
      </div>
    </div>
  );
}
