import type { RuntimeSettingsPatch } from "@/lib/api";

/** Stratégia név → PATCH kulcs a runtime DB-hez. */
export const STRATEGY_RUNTIME_PATCH_KEY: Record<string, keyof RuntimeSettingsPatch> = {
  top_signal_entries: "strategy_top_signal_entries_enabled",
};

export function strategyPatchKey(name: string): keyof RuntimeSettingsPatch | undefined {
  return STRATEGY_RUNTIME_PATCH_KEY[name];
}
