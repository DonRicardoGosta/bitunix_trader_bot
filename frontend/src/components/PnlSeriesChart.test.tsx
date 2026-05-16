import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PnlSeriesChart } from "./PnlSeriesChart";
import type { PnlSeriesResponse } from "@/lib/api";

function sample(overrides: Partial<PnlSeriesResponse> = {}): PnlSeriesResponse {
  return {
    lookback_hours: 6,
    bucket_hours: 1,
    window_start: "2026-05-16T04:00:00Z",
    window_end: "2026-05-16T10:00:00Z",
    positions_in_window: 1,
    sync_error: null,
    buckets: [
      { bucket_start: "2026-05-16T04:00:00Z", realized_pnl_usdt: "1" },
      { bucket_start: "2026-05-16T05:00:00Z", realized_pnl_usdt: "2" },
    ],
    cumulative: [
      { at: "2026-05-16T04:00:00Z", cumulative_pnl_usdt: "0" },
      { at: "2026-05-16T10:00:00Z", cumulative_pnl_usdt: "3" },
    ],
    kpis: {
      count: 1,
      realized_pnl_usdt: "3",
      wins: 1,
      losses: 0,
      win_rate_pct: "100",
      profit_factor: null,
      expectancy_usdt: null,
      max_drawdown_usdt: "0",
      avg_win_usdt: null,
      avg_loss_usdt: null,
    },
    ...overrides,
  };
}

describe("<PnlSeriesChart />", () => {
  it("shows pause hint on hover", async () => {
    const user = userEvent.setup();
    const { container, rerender } = render(<PnlSeriesChart data={sample()} />);

    await user.hover(container.firstElementChild!);
    expect(screen.getByText(/szünet \(egér fölött\)/)).toBeInTheDocument();

    rerender(
      <PnlSeriesChart
        data={sample({
          buckets: [
            { bucket_start: "2026-05-16T04:00:00Z", realized_pnl_usdt: "99" },
          ],
          cumulative: [
            { at: "2026-05-16T04:00:00Z", cumulative_pnl_usdt: "0" },
            { at: "2026-05-16T10:00:00Z", cumulative_pnl_usdt: "99" },
          ],
        })}
      />,
    );

    expect(screen.getByText(/szünet \(egér fölött\)/)).toBeInTheDocument();
  });
});
