import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TpSlTimingTables } from "./TpSlTimingTables";
import type { TpSlTimingStats } from "@/lib/api";

function emptyHours() {
  return Array.from({ length: 24 }, (_, hour) => ({
    hour,
    tp_count: 0,
    sl_count: 0,
  }));
}

function sample(): TpSlTimingStats {
  const by_hour = Array.from({ length: 24 }, (_, hour) => ({
    hour,
    tp_count: hour === 10 ? 3 : 0,
    sl_count: hour === 14 ? 1 : 0,
  }));
  const by_weekday = [
    { weekday: 0, label: "Hétfő", tp_count: 2, sl_count: 1 },
    { weekday: 1, label: "Kedd", tp_count: 1, sl_count: 0 },
    { weekday: 2, label: "Szerda", tp_count: 0, sl_count: 0 },
    { weekday: 3, label: "Csütörtök", tp_count: 0, sl_count: 0 },
    { weekday: 4, label: "Péntek", tp_count: 0, sl_count: 0 },
    { weekday: 5, label: "Szombat", tp_count: 0, sl_count: 0 },
    { weekday: 6, label: "Vasárnap", tp_count: 0, sl_count: 0 },
  ];
  return {
    timezone: "Europe/Budapest",
    classification_note: "note",
    total_tp: 3,
    total_sl: 1,
    by_hour,
    by_weekday,
    by_weekday_hour: by_weekday.map((d) => ({
      ...d,
      by_hour:
        d.weekday === 0
          ? by_hour.map((h) =>
              h.hour === 10 ? { ...h, tp_count: 2 } : { ...h, tp_count: 0, sl_count: 0 },
            )
          : emptyHours(),
    })),
  };
}

describe("<TpSlTimingTables />", () => {
  it("renders view mode selector and net result", () => {
    render(<TpSlTimingTables data={sample()} />);
    expect(screen.getByLabelText(/Nézet/i)).toBeInTheDocument();
    expect(screen.getByText("Aktuális nézet")).toBeInTheDocument();
    expect(screen.getByText("10:00")).toBeInTheDocument();
  });

  it("switches to weekday-only view", async () => {
    const user = userEvent.setup();
    render(<TpSlTimingTables data={sample()} />);
    await user.selectOptions(screen.getByLabelText(/Nézet/i), "weekdays");
    expect(screen.getByText("Hétfő")).toBeInTheDocument();
    expect(screen.queryByText("10:00")).not.toBeInTheDocument();
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
