import { describe, expect, it } from "vitest";
import { buildCsv } from "./csvExport";

describe("buildCsv", () => {
  it("escapes commas and quotes", () => {
    const csv = buildCsv(
      ["a", "b"],
      [
        ["plain", "x"],
        ["has,comma", 'say "hi"'],
      ],
    );
    expect(csv).toContain('"has,comma"');
    expect(csv).toContain('"say ""hi"""');
  });
});
