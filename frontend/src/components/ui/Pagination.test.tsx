import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Pagination, pageSlice, totalPages } from "./Pagination";

describe("Pagination helpers", () => {
  it("totalPages handles empty/negative input", () => {
    expect(totalPages(0, 10)).toBe(1);
    expect(totalPages(15, 10)).toBe(2);
    expect(totalPages(20, 10)).toBe(2);
    expect(totalPages(21, 10)).toBe(3);
    expect(totalPages(100, 0)).toBe(1);
  });

  it("pageSlice returns the right window", () => {
    const items = [1, 2, 3, 4, 5];
    expect(pageSlice(items, 1, 2)).toEqual([1, 2]);
    expect(pageSlice(items, 2, 2)).toEqual([3, 4]);
    expect(pageSlice(items, 3, 2)).toEqual([5]);
    expect(pageSlice(items, 99, 2)).toEqual([]);
  });
});

describe("<Pagination />", () => {
  it("renders range info and triggers callbacks", async () => {
    const onPageChange = vi.fn();
    render(
      <Pagination
        page={2}
        pageSize={10}
        totalItems={45}
        onPageChange={onPageChange}
      />,
    );
    // 11–20 / 45
    expect(screen.getByText(/11/)).toBeInTheDocument();
    expect(screen.getByText(/20/)).toBeInTheDocument();
    expect(screen.getByText(/45/)).toBeInTheDocument();
    // Klikk a "Következő oldal"-ra
    await userEvent.click(screen.getByLabelText(/Következő oldal/));
    expect(onPageChange).toHaveBeenCalledWith(3);
    // Az "Első oldal" 1-re ugrik
    await userEvent.click(screen.getByLabelText(/Első oldal/));
    expect(onPageChange).toHaveBeenLastCalledWith(1);
  });

  it("disables first/prev on page 1", () => {
    render(
      <Pagination
        page={1}
        pageSize={10}
        totalItems={50}
        onPageChange={() => {}}
      />,
    );
    expect(screen.getByLabelText(/Első oldal/)).toBeDisabled();
    expect(screen.getByLabelText(/Előző oldal/)).toBeDisabled();
    expect(screen.getByLabelText(/Következő oldal/)).not.toBeDisabled();
  });
});
