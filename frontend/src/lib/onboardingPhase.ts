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
  sentry_notifications: "advisory",
  approve_reject:       "supervised",
  auto_apply:           "auto",
  concierge_dashboard:  "advisory",
  email_signal_routing: "advisory",
};

export function phaseAllows(
  phase: OnboardingPhase | string | undefined,
  feature: keyof typeof FEATURE_GATES
): boolean {
  const p = (phase ?? "shadow") as OnboardingPhase;
  const required = FEATURE_GATES[feature];
  if (!required) return false;
  return PHASE_ORDER.indexOf(p) >= PHASE_ORDER.indexOf(required);
}

export const PHASE_LABELS: Record<OnboardingPhase, string> = {
  shadow:     "Shadow",
  advisory:   "Advisory",
  supervised: "Supervised",
  auto:       "Auto",
};

export const PHASE_DESCRIPTIONS: Record<OnboardingPhase, string> = {
  shadow:     "SENTINEL monitors and learns. Nothing surfaced to users.",
  advisory:   "Recommendations and notifications visible. No control writes.",
  supervised: "Controls enabled. Humans approve each action before it executes.",
  auto:       "SENTINEL acts automatically within defined safety limits.",
};

export const PHASE_COLORS: Record<OnboardingPhase, string> = {
  shadow:     "var(--color-sentinel-text-secondary)",
  advisory:   "#f59e0b",   // amber
  supervised: "#3b82f6",   // blue
  auto:       "var(--color-sentinel-green)",
};

export const ALL_PHASES: OnboardingPhase[] = ["shadow", "advisory", "supervised", "auto"];
