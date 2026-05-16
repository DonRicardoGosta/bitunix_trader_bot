import { describe, expect, it } from "vitest";
import { formatDurationSec } from "./formatDuration";

describe("formatDurationSec", () => {
  it("formats hours and minutes", () => {
    expect(formatDurationSec(3661)).toBe("1 óra 1 perc");
  });

  it("returns dash for null", () => {
    expect(formatDurationSec(null)).toBe("—");
  });
});
