import { useEffect, useMemo, useRef, useState } from "react";
import { Shield, AlertTriangle, Lock } from "lucide-react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
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

const HOLD_MS = 2000;

export function OnboardingPhaseSettings({
  selectedSiteId,
  sites,
  currentUserRole,
  readOnly,
  onError,
  onSuccess,
}: OnboardingPhaseSettingsProps) {
  const queryClient = useQueryClient();
  const [updating, setUpdating] = useState(false);
  const [selectedPhase, setSelectedPhase] = useState<OnboardingPhase | null>(null);
  const holdRef = useRef<{ timer: ReturnType<typeof setTimeout> | null; start: number }>({ timer: null, start: 0 });
  const [holdProgress, setHoldProgress] = useState(0);

  // Force cache invalidation when selected site changes or component mounts
  useEffect(() => {
    if (selectedSiteId) {
      // Invalidate buildings list cache to get fresh phase data
      queryClient.invalidateQueries({ queryKey: ['buildings-list'] });
    }
  }, [selectedSiteId, queryClient]);

  const selectedSite = useMemo(
    () => sites.find((site) => site.id === selectedSiteId) ?? null,
    [sites, selectedSiteId],
  );
  // Debug: log what phase we're receiving
  useEffect(() => {
    if (selectedSite) {
      console.log('[OnboardingPhaseSettings] Site:', selectedSite.id, 'Phase:', selectedSite.onboarding_phase);
    }
  }, [selectedSite]);
  const currentPhase = (selectedSite?.onboarding_phase as OnboardingPhase) ?? "shadow";
  const confirmPhase = selectedPhase ?? currentPhase;
  const locked = readOnly || !selectedSiteId;

  const handlePhaseSelect = (next: OnboardingPhase) => {
    if (next === currentPhase) {
      setSelectedPhase(null);
      setHoldProgress(0);
      return;
    }
    setSelectedPhase(next);
    setHoldProgress(0);
  };

  const startHold = () => {
    if (updating || locked || !selectedPhase || selectedPhase === currentPhase) return;
    holdRef.current.start = Date.now();
    const tick = () => {
      const elapsed = Date.now() - holdRef.current.start;
      setHoldProgress(Math.min(elapsed / HOLD_MS, 1));
      if (elapsed >= HOLD_MS) {
        setHoldProgress(0);
        commitChange(selectedPhase);
        return;
      }
      holdRef.current.timer = setTimeout(tick, 50);
    };
    tick();
  };

  const cancelHold = () => {
    if (holdRef.current.timer) {
      clearTimeout(holdRef.current.timer);
      holdRef.current.timer = null;
    }
    setHoldProgress(0);
  };

  const commitChange = async (phase: OnboardingPhase) => {
    if (!selectedSiteId) return;
    setUpdating(true);
    try {
      await api.updateSitePhase(selectedSiteId, phase);
      // Optimistically update the buildings-list cache so the new phase
      // appears immediately without waiting for the async refetch
      queryClient.setQueryData(['buildings-list', selectedSiteId], (old: any) => {
        if (!old) return old;
        return old.map?.((site: any) =>
          site.id === selectedSiteId ? { ...site, onboarding_phase: phase } : site
        ) ?? old;
      });
      queryClient.invalidateQueries({ queryKey: ['buildings-list'] });
      queryClient.invalidateQueries({ queryKey: ['site', selectedSiteId] });
      setSelectedPhase(null);
      onSuccess?.();
    } catch (error) {
      const msg =
        typeof error === "object" && error !== null && "message" in error
          ? String((error as { message: unknown }).message)
          : "Failed to update onboarding phase.";
      toast.error(msg, { description: "Site mode advancement blocked." });
      onError?.(msg);
      setSelectedPhase(null);
    } finally {
      setUpdating(false);
    }
  };

  return (
    <>
      <div className="glass-panel flat overflow-hidden">
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
            {locked ? (
              <div className="flex items-center gap-2 p-3 rounded" style={{ background: "rgba(220, 38, 38, 0.08)", border: "1px solid rgba(220, 38, 38, 0.2)" }}>
                <Lock className="h-4 w-4" style={{ color: "var(--color-sentinel-red)" }} />
                <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {currentUserRole !== "admin" ? "Unlock settings at the top of the page to change site mode." : "Select a site to change site mode."}
                </span>
              </div>
            ) : (
              <div className="flex items-center gap-3 flex-wrap">
                <select
                  value={confirmPhase}
                  disabled={updating}
                  onChange={(e) => handlePhaseSelect(e.target.value as OnboardingPhase)}
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

                {selectedPhase && selectedPhase !== currentPhase && (
                  <div className="flex items-center gap-2">
                    <button
                      onMouseDown={startHold}
                      onMouseUp={cancelHold}
                      onMouseLeave={cancelHold}
                      onTouchStart={startHold}
                      onTouchEnd={cancelHold}
                      disabled={updating}
                      className="relative px-4 py-2 rounded text-sm font-medium overflow-hidden select-none"
                      style={{
                        background: "rgba(220, 38, 38, 0.15)",
                        color: "var(--color-sentinel-red)",
                        border: "1px solid rgba(220, 38, 38, 0.3)",
                        cursor: updating ? "not-allowed" : "pointer",
                      }}
                    >
                      <span className="relative z-10 flex items-center gap-1.5">
                        <AlertTriangle className="h-3.5 w-3.5" />
                        Hold to Confirm
                      </span>
                      {holdProgress > 0 && (
                        <span
                          className="absolute inset-0 origin-left will-change-transform"
                          style={{
                            background: "rgba(220, 38, 38, 0.2)",
                            transform: `scaleX(${holdProgress})`,
                            transition: "transform 50ms linear",
                          }}
                        />
                      )}
                    </button>
                    <button
                      onClick={() => { setSelectedPhase(null); setHoldProgress(0); }}
                      disabled={updating}
                      className="px-3 py-2 rounded text-xs font-medium"
                      style={{
                        background: "var(--color-grafana-bg-secondary)",
                        border: "1px solid var(--color-grafana-border)",
                        color: "var(--color-grafana-text-secondary)",
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

export default OnboardingPhaseSettings;
