import { describe, expect, it } from "vitest";
import { cn, formatNumber, pnlClass } from "./utils";

describe("cn", () => {
  it("merges conditional class names", () => {
    expect(cn("a", false && "b", "c")).toBe("a c");
  });

  it("dedupes tailwind classes via twMerge", () => {
    expect(cn("px-2 px-4")).toBe("px-4");
  });
});

describe("formatNumber", () => {
  it("returns em dash for nullish", () => {
    expect(formatNumber(null)).toBe("—");
    expect(formatNumber(undefined)).toBe("—");
    expect(formatNumber("")).toBe("—");
  });

  it("formats with default 2 decimals", () => {
    expect(formatNumber(1234.5)).toBe("1,234.50");
  });

  it("respects decimals option", () => {
    expect(formatNumber(0.123456, { decimals: 4 })).toBe("0.1235");
  });

  it("adds explicit + sign when requested", () => {
    expect(formatNumber(2, { sign: true })).toBe("+2.00");
    expect(formatNumber(-2, { sign: true })).toBe("-2.00");
  });
});

describe("pnlClass", () => {
  it("colors profit green, loss red, zero neutral", () => {
    expect(pnlClass(1)).toBe("text-profit");
    expect(pnlClass(-1)).toBe("text-loss");
    expect(pnlClass(0)).toBe("text-muted");
  });
});
