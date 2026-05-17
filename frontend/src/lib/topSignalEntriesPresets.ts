import type { TopSignalEntriesConfig } from "@/lib/api";

/** Sok egyidejű pozíció / lazább szűrők — WF gate ki, magas scan/lookahead. */
export const PRESET_MANY_POSITIONS: TopSignalEntriesConfig = {
  count: 30,
  scan_limit_max: 1000,
  scan_limit: 800,
  kline_lookahead: 150,
  kline_interval: "15m",
  kline_limit: 80,
  cooldown_minutes: 90,
  min_abs_change_pct: "0.5",
  range_threshold: "0.55",
  max_kline_concurrency: 25,
  wf_gate_enabled: false,
  wf_lookback_minutes: 4320,
  wf_cooldown_minutes: 20,
  wf_choppiness_max: "2.0",
  margin_pct_of_balance: "0.01",
  min_margin_usdt: "0.2",
  tp_roi_pct: "200",
  sl_roi_pct: "100",
  min_tp_roi_pct: "0",
  tpsl_stop_type: "MARK_PRICE",
};

/** Több pozíció WF gate mellett — kompromisszum minőség és mennyiség között. */
export const PRESET_BALANCED_MANY: TopSignalEntriesConfig = {
  count: 20,
  scan_limit_max: 1000,
  scan_limit: 500,
  kline_lookahead: 100,
  kline_interval: "15m",
  kline_limit: 80,
  cooldown_minutes: 120,
  min_abs_change_pct: "0.8",
  range_threshold: "0.58",
  max_kline_concurrency: 20,
  wf_gate_enabled: true,
  wf_lookback_minutes: 4320,
  wf_cooldown_minutes: 30,
  wf_choppiness_max: "1.85",
  margin_pct_of_balance: "0.01",
  min_margin_usdt: "0.2",
  tp_roi_pct: "200",
  sl_roi_pct: "100",
  min_tp_roi_pct: "40",
  tpsl_stop_type: "MARK_PRICE",
};
