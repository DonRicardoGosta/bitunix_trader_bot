import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as apiMod from "@/lib/api";
import CoinAnalyzePage from "./page";

vi.mock("recharts", () => {
  const Box = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>;
  return {
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="recharts-wrap">{children}</div>
    ),
    ComposedChart: Box,
    Line: () => null,
    XAxis: () => null,
    YAxis: () => null,
    Tooltip: () => null,
    CartesianGrid: () => null,
    ReferenceArea: () => null,
    Legend: () => null,
  };
});

describe("CoinAnalyzePage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("megjeleníti a címet és betölti a szimbólumokat", async () => {
    vi.spyOn(apiMod.api, "marketSymbols").mockResolvedValue([
      { symbol: "BTCUSDT", max_leverage: 125 },
    ]);

    render(<CoinAnalyzePage />);

    expect(screen.getByRole("heading", { name: /Coin elemzés/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(apiMod.api.marketSymbols).toHaveBeenCalled();
    });
    await waitFor(() => {
      const sels = [...document.querySelectorAll("select")] as HTMLSelectElement[];
      const sym = sels.find((s) => [...s.options].some((o) => o.value === "BTCUSDT"));
      expect(sym?.value).toBe("BTCUSDT");
    });
  });
});
