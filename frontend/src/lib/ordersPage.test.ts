import { describe, expect, it } from "vitest";
import {
  ORDERS_REFRESH_INTERVAL_OPTIONS,
  isOrdersRefreshIntervalSec,
  ordersRefreshLabel,
} from "./ordersPage";

describe("ordersPage", () => {
  it("validates refresh interval options", () => {
    expect(isOrdersRefreshIntervalSec(60)).toBe(true);
    expect(isOrdersRefreshIntervalSec(10)).toBe(false);
    expect(ORDERS_REFRESH_INTERVAL_OPTIONS).toContain(60);
  });

  it("formats refresh labels", () => {
    expect(ordersRefreshLabel(60)).toBe("1 perc");
    expect(ordersRefreshLabel(30)).toBe("30 mp");
  });
});
