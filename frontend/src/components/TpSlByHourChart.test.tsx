import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { TpSlByHourChart } from "./TpSlByHourChart";
import type { TpSlByHourResponse } from "@/lib/api";

function sampleData(): TpSlByHourResponse {
  return {
    timezone: "Europe/Budapest",
    classification_note: "test note",
    total_tp: 2,
    total_sl: 1,
    hours: Array.from({ length: 24 }, (_, hour) => ({
      hour,
      tp_count: hour === 10 ? 2 : 0,
      sl_count: hour === 14 ? 1 : 0,
    })),
  };
}

describe("<TpSlByHourChart />", () => {
  it("renders totals and chart when data exists", () => {
    render(<TpSlByHourChart data={sampleData()} />);
    expect(screen.getByText(/2 TP/)).toBeInTheDocument();
    expect(screen.getByText(/1 SL/)).toBeInTheDocument();
    expect(screen.getByText(/test note/)).toBeInTheDocument();
  });

  it("shows empty state when no tp/sl", () => {
    render(
      <TpSlByHourChart
        data={{
          ...sampleData(),
          total_tp: 0,
          total_sl: 0,
        }}
      />,
    );
    expect(screen.getByText(/Nincs lezárt pozíció/)).toBeInTheDocument();
  });
});
