/* eslint-disable react-refresh/only-export-components */
import { useEffect, useMemo, useRef, useState } from 'react';
import * as React from 'react';
import { Lightbulb, X, Zap, ThermometerSun, Lamp, ChevronRight, CheckCircle2, Lock } from 'lucide-react';
import { toast } from 'sonner';
import { authorizedFetch } from '@/lib/api/client';
import { phaseAllows } from '@/lib/onboardingPhase';
import type { OnboardingPhase } from '@/lib/onboardingPhase';

// Equipment type → control module mapping for frontend gating
const EQUIPMENT_CONTROL_MODULE: Record<string, string> = {
  CHILLER: 'hvac_control', AHU: 'hvac_control', FCU: 'hvac_control',
  VAV: 'hvac_control', SPLIT: 'hvac_control', CT: 'hvac_control', CRAC: 'hvac_control',
  GEN: 'energy_control', UPS: 'energy_control', ATS: 'energy_control',
  TX: 'energy_control', MSB: 'energy_control', MTR: 'energy_control',
  DALI: 'lighting_control', LTG: 'lighting_control', LUM: 'lighting_control',
  INV: 'solar_control', BESS: 'solar_control', PV: 'solar_control',
  ACC: 'security_control', CCTV: 'security_control',
};

function getControlModuleForEquipment(equipmentCode: string): string | null {
  if (!equipmentCode) return null;
  const parts = equipmentCode.toUpperCase().split('-');
  if (parts.length < 2) return null;
  return EQUIPMENT_CONTROL_MODULE[parts[1]] ?? null;
}

interface RecommendationData {
  id: string;
  status: string;
  target_equipment: string;
  action_type: string;
  reason: string;
  action?: { point?: string; value?: number };
  expected_impact?: { description?: string; energy_savings_percent?: number };
  confidence: string;
  risk_level: string;
  profile: string;
  timestamp: string;
}

/**
 * Hook that polls for new recommendations and shows toast notifications.
 * Clicking a toast opens the recommendation detail card.
 */
export function useRecommendationToasts(
  siteId: string,
  onShowCard: (rec: RecommendationData) => void,
  pollingIntervalMs = 30000,
) {
  useEffect(() => {
    if (!siteId || siteId === 'site-001') return;

    // Persist seen IDs across polls within the session so dismissed recs don't re-toast
    const SESSION_KEY = `sentinel_seen_recs_${siteId}`;
    const shownToastIds = new Set<string>(
      JSON.parse(sessionStorage.getItem(SESSION_KEY) || '[]')
    );
    const persist = () => sessionStorage.setItem(SESSION_KEY, JSON.stringify([...shownToastIds]));

    const poll = async () => {
      try {
        // Backend route: GET /api/modules/site/{site_id}/recommendations
        // Returns a list directly (not {recommendations: [...]})
        const response = await authorizedFetch(`/api/modules/site/${siteId}/recommendations`);
        if (!response.ok) return;
        const data = await response.json();
        const items: RecommendationData[] = Array.isArray(data) ? data : (data.recommendations || []);

        const pending = items.filter(
          (r: RecommendationData) => r.status?.toLowerCase() === 'pending'
        );

        if (pending.length > 0) {
          for (const rec of pending) {
            if (!shownToastIds.has(rec.id)) {
              shownToastIds.add(rec.id);
              persist();

              toast("AI Recommendation", {
                description: `${rec.reason} — ${rec.target_equipment}`,
                duration: 10000,
                icon: <Lightbulb className="h-4 w-4" style={{ color: 'var(--color-sentinel-amber)' }} />,
                action: {
                  label: "View",
                  onClick: () => onShowCard(rec),
                },
              });
            }
          }
        }
      } catch (error) {
        console.error('Failed to fetch recommendations:', error);
      }
    };

    // Initial poll
    poll();
    const interval = setInterval(poll, pollingIntervalMs);
    return () => clearInterval(interval);
  }, [siteId, pollingIntervalMs, onShowCard]);
}

/**
 * Recommendation detail card — slides in from the right when a toast is clicked.
 */
export function RecommendationCard({
  recommendation,
  onClose,
  onApprove,
  controlActive,
  sitePhase,
}: {
  recommendation: RecommendationData;
  onClose: () => void;
  onApprove: (id: string) => void;
  controlActive?: boolean;
  sitePhase?: OnboardingPhase | string;
}) {
  // Auto-detect control module status from equipment code
  const resolvedControlActive = useMemo(() => {
    if (controlActive !== undefined) return controlActive;
    // Try to check via modules API — but to avoid hook dependency issues,
    // we'll check by fetching module status inline
    const controlModule = getControlModuleForEquipment(recommendation.target_equipment);
    if (!controlModule) return true; // Unknown equipment type — allow
    return true; // Default to true; backend enforces the real gate
  }, [controlActive, recommendation.target_equipment]);

  // Fetch actual module status on mount
  const [isControlActive, setIsControlActive] = React.useState(resolvedControlActive);
  React.useEffect(() => {
    const controlModule = getControlModuleForEquipment(recommendation.target_equipment);
    if (!controlModule || controlActive !== undefined) {
      setIsControlActive(controlActive ?? true);
      return;
    }
    authorizedFetch('/api/modules/status/' + (sessionStorage.getItem('sentinel_selected_site') || ''))
      .then(r => r.json())
      .then((modules: Array<{ module_type: string; status: string }>) => {
        const mod = modules.find((m) => m.module_type === controlModule);
        setIsControlActive(mod?.status === 'active');
      })
      .catch(() => setIsControlActive(true)); // Fail open — backend enforces
  }, [recommendation.target_equipment, controlActive]);

  const isHVAC = recommendation.action?.point?.includes('setpoint') || recommendation.action?.point?.includes('cooling');
  const isLighting = recommendation.action?.point?.includes('lighting') || recommendation.action?.point?.includes('dimming');

  const Icon = isHVAC ? ThermometerSun : isLighting ? Lamp : Zap;
  const iconColor = isHVAC ? 'var(--color-sentinel-blue)' : isLighting ? 'var(--color-sentinel-amber)' : 'var(--color-sentinel-green)';
  const savings = recommendation.expected_impact?.energy_savings_percent ?? 0;

  // Swipe-to-dismiss (left swipe = read/close)
  const touchStartX = useRef<number | null>(null);
  const [swipeOffset, setSwipeOffset] = useState(0);
  const [swiping, setSwiping] = useState(false);
  const SWIPE_THRESHOLD = 80;

  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX;
    setSwiping(true);
  };
  const handleTouchMove = (e: React.TouchEvent) => {
    if (touchStartX.current === null) return;
    const delta = e.touches[0].clientX - touchStartX.current;
    // Only track leftward swipe (negative delta)
    setSwipeOffset(Math.min(0, delta));
  };
  const handleTouchEnd = () => {
    if (swipeOffset < -SWIPE_THRESHOLD) {
      onClose(); // swipe-to-dismiss = mark as read
    } else {
      setSwipeOffset(0);
    }
    setSwiping(false);
    touchStartX.current = null;
  };

  return (
    <div
      className="fixed right-4 top-4 z-50 w-96 rounded-lg shadow-2xl overflow-hidden"
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      style={{
        background: 'var(--color-sentinel-bg-panel, #1a1a2e)',
        border: '1px solid var(--color-sentinel-border, #2a2a4a)',
        animation: swiping ? 'none' : 'slideInRight 0.3s ease-out',
        transform: `translateX(${swipeOffset}px)`,
        transition: swiping ? 'none' : 'transform 0.2s ease-out',
        opacity: swipeOffset < -20 ? 1 - Math.min(1, (-swipeOffset - 20) / 80) : 1,
      }}
    >
      {/* Header */}
      <div
        className="px-4 py-3 flex items-center justify-between"
        style={{ borderBottom: '1px solid var(--color-sentinel-border, #2a2a4a)' }}
      >
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded" style={{ background: `${iconColor}20` }}>
            <Icon className="h-4 w-4" style={{ color: iconColor }} />
          </div>
          <span className="font-medium text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>
            AI Recommendation
          </span>
        </div>
        <button onClick={onClose} className="p-1 rounded hover:bg-white/10 transition-colors" aria-label="Dismiss recommendation">
          <X className="h-4 w-4" style={{ color: 'var(--color-sentinel-text-secondary)' }} />
        </button>
      </div>

      {/* Body */}
      <div className="p-4 space-y-3">
        {/* Equipment */}
        <div>
          <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            Equipment
          </span>
          <div className="font-mono text-sm mt-0.5" style={{ color: 'var(--color-sentinel-text-primary)' }}>
            {recommendation.target_equipment}
          </div>
        </div>

        {/* Reason */}
        <div>
          <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            Finding
          </span>
          <div className="text-sm mt-0.5" style={{ color: 'var(--color-sentinel-text-primary)' }}>
            {recommendation.reason}
          </div>
        </div>

        {/* Action */}
        {recommendation.action && (
          <div
            className="p-3 rounded"
            style={{ background: 'var(--color-sentinel-bg-secondary, #111128)' }}
          >
            <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              Proposed Action
            </span>
            <div className="flex items-center gap-2 mt-1">
              <ChevronRight className="h-3 w-3" style={{ color: iconColor }} />
              <span className="text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                Set <span className="font-mono">{recommendation.action.point}</span> to{' '}
                <span className="font-bold" style={{ color: iconColor }}>
                  {recommendation.action.value}
                  {isHVAC ? '°C' : isLighting ? '%' : ''}
                </span>
              </span>
            </div>
          </div>
        )}

        {/* Impact */}
        {recommendation.expected_impact && (
          <div className="flex items-center gap-3">
            <div
              className="flex-1 p-2 rounded text-center"
              style={{ background: 'rgba(16, 185, 129, 0.1)' }}
            >
              <div className="text-lg font-bold" style={{ color: 'var(--color-sentinel-green)' }}>
                {savings}%
              </div>
              <div className="text-[10px]" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Energy Savings
              </div>
            </div>
            <div
              className="flex-1 p-2 rounded text-center"
              style={{ background: 'rgba(59, 130, 246, 0.1)' }}
            >
              <div className="text-lg font-bold" style={{ color: 'var(--color-sentinel-blue)' }}>
                {recommendation.confidence}
              </div>
              <div className="text-[10px]" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Confidence
              </div>
            </div>
            <div
              className="flex-1 p-2 rounded text-center"
              style={{ background: 'rgba(16, 185, 129, 0.1)' }}
            >
              <div className="text-lg font-bold" style={{ color: 'var(--color-sentinel-green)' }}>
                {recommendation.risk_level}
              </div>
              <div className="text-[10px]" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Risk Level
              </div>
            </div>
          </div>
        )}

        {/* Timestamp + AI disclosure */}
        <div className="text-[10px]" style={{ color: 'var(--color-sentinel-text-disabled, #666)' }}>
          <span className="text-sky-400/70">AI-generated</span> &middot; Detected at {new Date(recommendation.timestamp).toLocaleTimeString()} — Profile: {recommendation.profile}
        </div>
      </div>

      {/* Footer */}
      <div
        className="px-4 py-3 flex flex-col gap-2"
        style={{ borderTop: '1px solid var(--color-sentinel-border, #2a2a4a)' }}
      >
        {!isControlActive && (
          <div
            className="flex items-center gap-2 px-3 py-2 rounded text-xs"
            style={{ background: 'rgba(250, 204, 21, 0.1)', color: 'var(--color-sentinel-amber)' }}
          >
            <Lock className="h-3 w-3 flex-shrink-0" />
            <span>Control module not active. Enable the control add-on to execute recommendations.</span>
          </div>
        )}
        {isControlActive && !phaseAllows(sitePhase, "approve_reject") && (
          <div
            className="flex items-center gap-2 px-3 py-2 rounded text-xs"
            style={{ background: 'rgba(59, 130, 246, 0.1)', color: 'var(--color-sentinel-blue)' }}
          >
            <Lock className="h-3 w-3 flex-shrink-0" />
            <span>Advisory mode — recommendations are view-only. Upgrade to supervised to approve.</span>
          </div>
        )}
        <div className="flex gap-2">
          {isControlActive && phaseAllows(sitePhase, "approve_reject") ? (
            <button
              onClick={() => { onApprove(recommendation.id); onClose(); }}
              className="flex-1 py-2 rounded text-sm font-medium flex items-center justify-center gap-1.5 transition-colors hover:brightness-110"
              style={{ background: 'var(--color-sentinel-green)', color: 'white' }}
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              Approve & Execute
            </button>
          ) : !isControlActive ? (
            <button
              disabled
              className="flex-1 py-2 rounded text-sm font-medium flex items-center justify-center gap-1.5 opacity-50 cursor-not-allowed"
              style={{ background: 'var(--color-sentinel-text-disabled)', color: 'white' }}
            >
              <Lock className="h-3.5 w-3.5" />
              Control Module Required
            </button>
          ) : null}
          <button
            onClick={onClose}
            className="px-4 py-2 rounded text-sm transition-colors hover:bg-white/10"
            style={{ color: 'var(--color-sentinel-text-secondary)', border: '1px solid var(--color-sentinel-border, #2a2a4a)' }}
          >
            Dismiss
          </button>
        </div>
      </div>

      {/* Swipe hint — touch only */}
      <div
        className="flex items-center justify-center py-1.5 gap-1.5"
        style={{
          borderTop: '1px solid var(--color-sentinel-border, #2a2a4a)',
          opacity: 0.4,
        }}
      >
        <span style={{ fontSize: '0.6rem', color: 'var(--color-sentinel-text-secondary)', letterSpacing: '0.05em' }}>
          ← swipe to dismiss
        </span>
      </div>

      <style>{`
        @keyframes slideInRight {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
      `}</style>
    </div>
  );
}

/**
 * Simple component that renders recommendation count badge.
 */
export function RecommendationBadge({ siteId }: { siteId: string }) {
  const [pendingCount, setPendingCount] = React.useState(0);

  React.useEffect(() => {
    if (!siteId || siteId === 'site-001') {
      setPendingCount(0);
      return;
    }
    const poll = async () => {
      try {
        const response = await authorizedFetch(`/api/modules/site/${siteId}/recommendations`);
        if (!response.ok) return;
        const data = await response.json();
        const items: RecommendationData[] = Array.isArray(data) ? data : (data.recommendations || []);
        const pending = items.filter((r: RecommendationData) => r.status?.toLowerCase() === 'pending');
        setPendingCount(pending.length);
      } catch (error) {
        console.error('Failed to fetch recommendation count:', error);
      }
    };
    poll();
    const timer = setInterval(poll, 30000);
    return () => clearInterval(timer);
  }, [siteId]);

  if (pendingCount === 0) return null;

  return (
    <div className="absolute top-2 right-2 bg-blue-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs font-bold">
      {pendingCount}
    </div>
  );
}
