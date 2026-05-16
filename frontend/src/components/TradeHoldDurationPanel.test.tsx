import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { TradeHoldDurationPanel } from "./TradeHoldDurationPanel";
import type { TradeHoldDurationStats } from "@/lib/api";

function sample(): TradeHoldDurationStats {
  const side = (count: number, avg: number) => ({
    wins: { count, avg_duration_sec: avg },
    losses: { count: 0, avg_duration_sec: null },
  });
  return {
    timezone: "Europe/Budapest",
    classification_note: "note",
    skipped_no_duration: 0,
    summary: {
      wins: { count: 2, avg_duration_sec: 3600 },
      losses: { count: 1, avg_duration_sec: 1800 },
    },
    by_weekday: [
      {
        weekday: 0,
        label: "Hétfő",
        wins: { count: 2, avg_duration_sec: 3600 },
        losses: { count: 1, avg_duration_sec: 1800 },
      },
    ],
    by_hour: [
      {
        hour: 10,
        wins: { count: 2, avg_duration_sec: 3600 },
        losses: { count: 1, avg_duration_sec: 1800 },
      },
    ],
  };
}

describe("<TradeHoldDurationPanel />", () => {
  it("renders summary and weekday table", () => {
    render(<TradeHoldDurationPanel data={sample()} />);
    expect(screen.getByText(/Nyertes trade átlag tartam/)).toBeInTheDocument();
    expect(screen.getAllByText(/1 óra/).length).toBeGreaterThan(0);
    expect(screen.getByText("Hétfő")).toBeInTheDocument();
  });
});
