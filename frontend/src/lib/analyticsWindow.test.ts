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

  it("builds live cache key without fixed end", () => {
    const live = analyticsQueryCacheKey({
      mode: "custom",
      windowStart: "2026-05-01T00:00:00.000Z",
      endLive: true,
      bucketHours: 6,
    });
    const fixed = analyticsQueryCacheKey({
      mode: "custom",
      windowStart: "2026-05-01T00:00:00.000Z",
      endLive: false,
      windowEnd: "2026-05-02T00:00:00.000Z",
      bucketHours: 6,
    });
    expect(live).toContain(":live:");
    expect(live).not.toContain("2026-05-02");
    expect(fixed).toContain("2026-05-02");
  });
});
