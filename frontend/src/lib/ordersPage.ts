/** Rendelések oldal – saját frissítési intervallum (nem a globális Navbar). */

export const ORDERS_REFRESH_INTERVAL_OPTIONS = [30, 60, 120, 300] as const;

export type OrdersRefreshIntervalSec =
  (typeof ORDERS_REFRESH_INTERVAL_OPTIONS)[number];

export function isOrdersRefreshIntervalSec(n: number): n is OrdersRefreshIntervalSec {
  return (ORDERS_REFRESH_INTERVAL_OPTIONS as readonly number[]).includes(n);
}

export function ordersRefreshLabel(sec: number): string {
  if (sec < 60) return `${sec} mp`;
  if (sec % 60 === 0) return `${sec / 60} perc`;
  return `${sec} mp`;
}
