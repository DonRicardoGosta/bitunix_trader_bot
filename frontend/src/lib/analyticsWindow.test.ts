import { describe, expect, it } from "vitest";
import {
  analyticsQueryCacheKey,
  datetimeLocalValueToIso,
  isoToDatetimeLocalValue,
} from "./analyticsWindow";

describe("analyticsWindow", () => {
  it("round-trips datetime-local via ISO", () => {
    const iso = "2026-05-10T14:30:00.000Z";
    const local = isoToDatetimeLocalValue(iso);
    const back = datetimeLocalValueToIso(local);
    expect(back).toBeTruthy();
    expect(new Date(back!).getTime()).toBe(new Date(iso).getTime());
  });

  it("builds distinct cache keys for custom vs preset", () => {
    const a = analyticsQueryCacheKey({
      mode: "preset",
      lookbackHours: 24,
      bucketHours: 6,
    });
    const b = analyticsQueryCacheKey({
      mode: "custom",
      windowStart: "2026-05-01T00:00:00.000Z",
      windowEnd: "2026-05-02T00:00:00.000Z",
      bucketHours: 6,
    });
    expect(a).not.toBe(b);
  });
});
