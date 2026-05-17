import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TopSignalEntriesConfigEditor } from "./TopSignalEntriesConfigEditor";
import type { TopSignalEntriesConfig } from "@/lib/api";

const DEFAULT: TopSignalEntriesConfig = {
  count: 10,
  scan_limit_max: 1000,
  scan_limit: 1000,
  kline_lookahead: 1000,
  kline_interval: "15m",
  kline_limit: 80,
  cooldown_minutes: 240,
  min_abs_change_pct: "1.0",
  range_threshold: "0.60",
  max_kline_concurrency: 10,
  wf_gate_enabled: true,
  wf_lookback_minutes: 4320,
  wf_cooldown_minutes: 60,
  wf_choppiness_max: "1.72",
  margin_pct_of_balance: "0.01",
  min_margin_usdt: "0.2",
  tp_roi_pct: "200",
  sl_roi_pct: "100",
  min_tp_roi_pct: "60",
  tpsl_stop_type: "MARK_PRICE",
};

const putMock = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    putTopSignalEntriesConfig: (...args: unknown[]) => putMock(...args),
  },
}));

describe("<TopSignalEntriesConfigEditor />", () => {
  beforeEach(() => {
    putMock.mockReset();
    putMock.mockResolvedValue({ config: { ...DEFAULT, count: 5 } });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("sends patch on save when count changes", async () => {
    render(<TopSignalEntriesConfigEditor initial={DEFAULT} />);
    const countInput = screen.getByLabelText(/Max\. párhuzamos pozíció/i);
    await userEvent.clear(countInput);
    await userEvent.type(countInput, "5");
    await userEvent.click(screen.getByRole("button", { name: /Paraméterek mentése/i }));
    await waitFor(() => expect(putMock).toHaveBeenCalledWith({ count: 5 }));
  });
});
