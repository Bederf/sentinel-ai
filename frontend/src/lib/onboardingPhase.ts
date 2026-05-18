/**
 * Onboarding Phase — SENTINEL trust-building model (frontend)
 *
 * Mirrors backend: app/models/onboarding_phase.py
 *
 * Phases progress: shadow → advisory → supervised → auto
 *
 * Use phaseAllows() in all components to gate feature visibility.
 * Single source of truth — do not duplicate gate logic in components.
 */

export type OnboardingPhase = "shadow" | "advisory" | "supervised" | "auto";

const PHASE_ORDER: OnboardingPhase[] = ["shadow", "advisory", "supervised", "auto"];

const FEATURE_GATES: Record<string, OnboardingPhase> = {
  recommendations_ui:   "advisory",
  sentry_notifications: "shadow",
  approve_reject:       "supervised",
  auto_apply:           "auto",
  concierge_dashboard:  "advisory",
  email_signal_routing: "advisory",
};

export function phaseAllows(
  phase: OnboardingPhase | string | undefined,
  feature: keyof typeof FEATURE_GATES
): boolean {
  const p = phase ?? "shadow";
  // Normalize shadow_live → shadow (live shadow mode)
  const normalized = p === "shadow_live" ? "shadow" : p;
  const required = FEATURE_GATES[feature as keyof typeof FEATURE_GATES];
  if (!required) return false;
  return PHASE_ORDER.indexOf(normalized as OnboardingPhase) >= PHASE_ORDER.indexOf(required);
}

export const PHASE_LABELS: Record<OnboardingPhase | string, string> = {
  shadow:      "Shadow",
  shadow_live: "Shadow",
  advisory:    "Advisory",
  supervised:  "Supervised",
  auto:        "Auto",
};

export const PHASE_DESCRIPTIONS: Record<OnboardingPhase | string, string> = {
  shadow:      "SENTINEL monitors and learns. Nothing surfaced to users.",
  shadow_live: "Live shadow mode with real-time data ingestion.",
  advisory:    "Recommendations and notifications visible. No control writes.",
  supervised:  "Controls enabled. Humans approve each action before it executes.",
  auto:        "SENTINEL acts automatically within defined safety limits.",
};

export const PHASE_COLORS: Record<OnboardingPhase | string, string> = {
  shadow:      "var(--color-sentinel-text-secondary)",
  shadow_live: "var(--color-sentinel-text-secondary)",
  advisory:    "#f59e0b",   // amber
  supervised:  "#3b82f6",   // blue
  auto:        "var(--color-sentinel-green)",
};

export const ALL_PHASES: OnboardingPhase[] = ["shadow", "advisory", "supervised", "auto"];
