import { useMemo, useState } from "react";
import { Shield } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { ALL_PHASES, PHASE_COLORS, PHASE_DESCRIPTIONS, PHASE_LABELS, type OnboardingPhase } from "@/lib/onboardingPhase";

interface SiteLike {
  id: string;
  name: string;
  onboarding_phase?: OnboardingPhase;
}

interface OnboardingPhaseSettingsProps {
  selectedSiteId?: string;
  sites: SiteLike[];
  currentUserRole: string;
  readOnly?: boolean;
  onError?: (error: string) => void;
  onSuccess?: () => void;
}

export function OnboardingPhaseSettings({
  selectedSiteId,
  sites,
  currentUserRole,
  readOnly,
  onError,
  onSuccess,
}: OnboardingPhaseSettingsProps) {
  const [updating, setUpdating] = useState(false);

  const selectedSite = useMemo(
    () => sites.find((site) => site.id === selectedSiteId) ?? null,
    [sites, selectedSiteId],
  );
  const currentPhase = (selectedSite?.onboarding_phase as OnboardingPhase) ?? "shadow";
  const isAdmin = currentUserRole === "admin";

  const handlePhaseChange = async (nextPhase: OnboardingPhase) => {
    if (!selectedSiteId) {
      onError?.("Select a site before changing onboarding phase.");
      return;
    }
    if (!isAdmin || readOnly) {
      onError?.("Only admins can change onboarding phase.");
      return;
    }
    if (nextPhase === currentPhase) {
      return;
    }
    setUpdating(true);
    try {
      await api.updateSitePhase(selectedSiteId, nextPhase);
      onSuccess?.();
    } catch (error) {
      const msg =
        typeof error === "object" && error !== null && "message" in error
          ? String((error as { message: unknown }).message)
          : "Failed to update onboarding phase.";
      toast.error(msg, { description: "Site mode advancement blocked." });
      onError?.(msg);
    } finally {
      setUpdating(false);
    }
  };

  return (
    <>
      <div className="glass-panel overflow-hidden">
        <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(59, 130, 246, 0.15)", color: "var(--color-sentinel-blue)" }}>
              <Shield className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Site Mode
              </h2>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Admin-only, site-gated phase control.
              </p>
            </div>
          </div>
        </div>
        <div className="p-4 space-y-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div>
              <p className="text-xs uppercase tracking-wider" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Current Site
              </p>
              <p className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {selectedSite?.name || selectedSiteId || "No site selected"}
              </p>
            </div>
            <div
              className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium"
              style={{
                backgroundColor: `${PHASE_COLORS[currentPhase]}22`,
                color: PHASE_COLORS[currentPhase],
                border: `1px solid ${PHASE_COLORS[currentPhase]}44`,
              }}
              title={PHASE_DESCRIPTIONS[currentPhase]}
            >
              {PHASE_LABELS[currentPhase]}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
              Site Mode
            </label>
            <select
              value={currentPhase}
              disabled={updating || !isAdmin || readOnly || !selectedSiteId}
              onChange={(e) => void handlePhaseChange(e.target.value as OnboardingPhase)}
              className="w-full md:w-64 rounded-md appearance-none cursor-pointer pl-3 pr-3 py-2.5 text-sm transition-colors focus:outline-none focus:ring-0"
              style={{
                background: "var(--color-grafana-bg-secondary)",
                border: "1px solid var(--color-grafana-border)",
                color: "var(--color-grafana-text-primary)",
                boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
                opacity: updating ? 0.6 : 1,
              }}
              title="Set SENTINEL onboarding phase for this site"
            >
              {ALL_PHASES.map((phase) => (
                <option key={phase} value={phase}>
                  {PHASE_LABELS[phase]}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>
    </>
  );
}

export default OnboardingPhaseSettings;
