import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { TpSlTimingTables } from "./TpSlTimingTables";
import type { TpSlTimingStats } from "@/lib/api";

function sample(): TpSlTimingStats {
  return {
    timezone: "Europe/Budapest",
    classification_note: "note",
    total_tp: 3,
    total_sl: 1,
    by_hour: Array.from({ length: 24 }, (_, hour) => ({
      hour,
      tp_count: hour === 10 ? 3 : 0,
      sl_count: hour === 14 ? 1 : 0,
    })),
    by_weekday: [
      { weekday: 0, label: "Hétfő", tp_count: 2, sl_count: 1 },
      { weekday: 1, label: "Kedd", tp_count: 1, sl_count: 0 },
      { weekday: 2, label: "Szerda", tp_count: 0, sl_count: 0 },
      { weekday: 3, label: "Csütörtök", tp_count: 0, sl_count: 0 },
      { weekday: 4, label: "Péntek", tp_count: 0, sl_count: 0 },
      { weekday: 5, label: "Szombat", tp_count: 0, sl_count: 0 },
      { weekday: 6, label: "Vasárnap", tp_count: 0, sl_count: 0 },
    ],
  };
}

describe("<TpSlTimingTables />", () => {
  it("renders hour and weekday tables", () => {
    render(<TpSlTimingTables data={sample()} />);
    expect(screen.getByText(/Óra szerint/)).toBeInTheDocument();
    expect(screen.getByText(/Hét napja szerint/)).toBeInTheDocument();
    expect(screen.getByText("Hétfő")).toBeInTheDocument();
    expect(screen.getByText("10:00")).toBeInTheDocument();
  });

  it("shows empty state", () => {
    render(
      <TpSlTimingTables
        data={{ ...sample(), total_tp: 0, total_sl: 0 }}
      />,
    );
    expect(screen.getByText(/Nincs lezárt pozíció/)).toBeInTheDocument();
  });
});
