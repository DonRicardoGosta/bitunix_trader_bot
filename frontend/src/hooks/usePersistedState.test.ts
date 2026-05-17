import { afterEach, describe, expect, it } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { usePersistedState, usePersistedStringState } from "./usePersistedState";

const KEY = "test_persisted_num";
const STR_KEY = "test_persisted_str";

afterEach(() => {
  localStorage.removeItem(KEY);
  localStorage.removeItem(STR_KEY);
});

describe("usePersistedState", () => {
  it("reads and writes localStorage", async () => {
    localStorage.setItem(KEY, "12");
    const { result } = renderHook(() =>
      usePersistedState(KEY, 24, (n) => n > 0 && n < 100),
    );
    await waitFor(() => {
      expect(result.current[0]).toBe(12);
    });
    act(() => {
      result.current[1](6);
    });
    expect(result.current[0]).toBe(6);
    expect(localStorage.getItem(KEY)).toBe("6");
  });
});

describe("usePersistedStringState", () => {
  const isAlpha = (v: string): v is "a" | "b" =>
    v === "a" || v === "b";

  it("hydrates from localStorage after mount", async () => {
    localStorage.setItem(STR_KEY, "b");
    const { result } = renderHook(() =>
      usePersistedStringState(STR_KEY, "a", isAlpha),
    );
    await waitFor(() => {
      expect(result.current[0]).toBe("b");
    });
  });

  it("does not loop when isValid identity changes each render", async () => {
    localStorage.setItem(STR_KEY, "b");
    const { result, rerender } = renderHook(
      ({ isValid }) => usePersistedStringState(STR_KEY, "a", isValid),
      {
        initialProps: {
          isValid: (v: string): v is "a" | "b" => v === "a" || v === "b",
        },
      },
    );
    await waitFor(() => {
      expect(result.current[0]).toBe("b");
    });
    rerender({
      isValid: (v: string): v is "a" | "b" => v === "a" || v === "b",
    });
    rerender({
      isValid: (v: string): v is "a" | "b" => v === "a" || v === "b",
    });
    expect(result.current[0]).toBe("b");
  });
});
