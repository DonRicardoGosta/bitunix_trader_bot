import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatCard } from "./StatCard";

describe("<StatCard />", () => {
  it("renders label, value, unit, and hint", () => {
    render(
      <StatCard
        label="Nyitott PnL"
        value="+12.34"
        unit="USDT"
        hint="3 nyitott pozíción"
      />,
    );
    expect(screen.getByText("Nyitott PnL")).toBeInTheDocument();
    expect(screen.getByText("+12.34")).toBeInTheDocument();
    expect(screen.getByText("USDT")).toBeInTheDocument();
    expect(screen.getByText("3 nyitott pozíción")).toBeInTheDocument();
  });

  it("applies tone colors", () => {
    const { container } = render(
      <StatCard label="x" value="1" tone="positive" />,
    );
    expect(container.querySelector(".text-profit")).toBeInTheDocument();
  });

  it("shows loader when loading", () => {
    render(<StatCard label="x" value="1" loading />);
    // Loader (animate-pulse) helyettesíti a num span-t
    expect(document.querySelector(".animate-pulse")).toBeInTheDocument();
  });
});
