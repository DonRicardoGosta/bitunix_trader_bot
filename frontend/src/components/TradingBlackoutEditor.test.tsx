import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { TradingBlackoutEditor } from "@/components/TradingBlackoutEditor";
import { defaultTradingBlackoutSchedule } from "@/lib/tradingBlackout";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  api: {
    putTradingBlackout: vi.fn(),
  },
}));

describe("TradingBlackoutEditor", () => {
  beforeEach(() => {
    vi.mocked(api.putTradingBlackout).mockReset();
  });

  it("keeps block_ranges UI when initial prop updates during edit", async () => {
    const user = userEvent.setup();
    const initial = defaultTradingBlackoutSchedule();
    const { rerender } = render(
      <TradingBlackoutEditor initial={initial} />,
    );

    const mondaySelect = screen.getAllByRole("combobox")[0];
    await user.selectOptions(mondaySelect, "block_ranges");

    await waitFor(() => {
      expect(screen.getAllByDisplayValue("22:00").length).toBeGreaterThan(0);
    });

    const refreshed = {
      ...defaultTradingBlackoutSchedule(),
      days: {
        ...defaultTradingBlackoutSchedule().days,
        monday: { mode: "open" as const, block_ranges: [] },
      },
    };
    rerender(<TradingBlackoutEditor initial={refreshed} />);

    expect(screen.getAllByDisplayValue("22:00").length).toBeGreaterThan(0);
    expect(mondaySelect).toHaveValue("block_ranges");
  });

  it("syncs from server when not dirty", async () => {
    const initial = defaultTradingBlackoutSchedule();
    const { rerender } = render(<TradingBlackoutEditor initial={initial} />);

    const mondaySelect = screen.getAllByRole("combobox")[0];
    expect(mondaySelect).toHaveValue("open");

    const refreshed = {
      ...defaultTradingBlackoutSchedule(),
      days: {
        ...defaultTradingBlackoutSchedule().days,
        monday: { mode: "block_all" as const, block_ranges: [] },
      },
    };
    rerender(<TradingBlackoutEditor initial={refreshed} />);

    expect(screen.getAllByRole("combobox")[0]).toHaveValue("block_all");
  });
});
