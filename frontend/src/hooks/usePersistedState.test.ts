import { afterEach, describe, expect, it } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { usePersistedState } from "./usePersistedState";

const KEY = "test_persisted_num";

afterEach(() => {
  localStorage.removeItem(KEY);
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
