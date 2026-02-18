import { useEffect, useState, useCallback } from 'react';
import * as React from 'react';
import { Lightbulb, X, Zap, ThermometerSun, Lamp, ChevronRight, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';

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
    if (!siteId) return;
    const shownToastIds = new Set<string>();

    const poll = async () => {
      try {
        const response = await fetch(`/api/recommendations/${siteId}`);
        const data = await response.json();

        const pending: RecommendationData[] = data.recommendations?.filter(
          (r: RecommendationData) => r.status?.toLowerCase() === 'pending'
        ) || [];

        if (pending.length > 0) {
          for (const rec of pending) {
            if (!shownToastIds.has(rec.id)) {
              shownToastIds.add(rec.id);

              toast("AI Recommendation", {
                description: `${rec.reason} — ${rec.target_equipment}`,
                duration: 10000,
                icon: <Lightbulb className="h-4 w-4" style={{ color: '#FACC15' }} />,
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
}: {
  recommendation: RecommendationData;
  onClose: () => void;
  onApprove: (id: string) => void;
}) {
  const isHVAC = recommendation.action?.point?.includes('setpoint') || recommendation.action?.point?.includes('cooling');
  const isDALI = recommendation.action?.point?.includes('lighting') || recommendation.action?.point?.includes('dimming');

  const Icon = isHVAC ? ThermometerSun : isDALI ? Lamp : Zap;
  const iconColor = isHVAC ? '#3B82F6' : isDALI ? '#FACC15' : '#10B981';
  const savings = recommendation.expected_impact?.energy_savings_percent ?? 0;

  return (
    <div
      className="fixed right-4 top-20 z-50 w-96 rounded-lg shadow-2xl overflow-hidden"
      style={{
        background: 'var(--color-sentinel-bg-panel, #1a1a2e)',
        border: '1px solid var(--color-sentinel-border, #2a2a4a)',
        animation: 'slideInRight 0.3s ease-out',
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
          <span className="font-medium text-sm" style={{ color: 'var(--color-sentinel-text-primary, #fff)' }}>
            AI Recommendation
          </span>
        </div>
        <button onClick={onClose} className="p-1 rounded hover:bg-white/10 transition-colors">
          <X className="h-4 w-4" style={{ color: 'var(--color-sentinel-text-secondary, #aaa)' }} />
        </button>
      </div>

      {/* Body */}
      <div className="p-4 space-y-3">
        {/* Equipment */}
        <div>
          <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary, #aaa)' }}>
            Equipment
          </span>
          <div className="font-mono text-sm mt-0.5" style={{ color: 'var(--color-sentinel-text-primary, #fff)' }}>
            {recommendation.target_equipment}
          </div>
        </div>

        {/* Reason */}
        <div>
          <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary, #aaa)' }}>
            Finding
          </span>
          <div className="text-sm mt-0.5" style={{ color: 'var(--color-sentinel-text-primary, #fff)' }}>
            {recommendation.reason}
          </div>
        </div>

        {/* Action */}
        {recommendation.action && (
          <div
            className="p-3 rounded"
            style={{ background: 'var(--color-sentinel-bg-secondary, #111128)' }}
          >
            <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary, #aaa)' }}>
              Proposed Action
            </span>
            <div className="flex items-center gap-2 mt-1">
              <ChevronRight className="h-3 w-3" style={{ color: iconColor }} />
              <span className="text-sm" style={{ color: 'var(--color-sentinel-text-primary, #fff)' }}>
                Set <span className="font-mono">{recommendation.action.point}</span> to{' '}
                <span className="font-bold" style={{ color: iconColor }}>
                  {recommendation.action.value}
                  {isHVAC ? '°C' : isDALI ? '%' : ''}
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
              <div className="text-lg font-bold" style={{ color: 'var(--color-sentinel-green, #10B981)' }}>
                {savings}%
              </div>
              <div className="text-[10px]" style={{ color: 'var(--color-sentinel-text-secondary, #aaa)' }}>
                Energy Savings
              </div>
            </div>
            <div
              className="flex-1 p-2 rounded text-center"
              style={{ background: 'rgba(59, 130, 246, 0.1)' }}
            >
              <div className="text-lg font-bold" style={{ color: '#3B82F6' }}>
                {recommendation.confidence}
              </div>
              <div className="text-[10px]" style={{ color: 'var(--color-sentinel-text-secondary, #aaa)' }}>
                Confidence
              </div>
            </div>
            <div
              className="flex-1 p-2 rounded text-center"
              style={{ background: 'rgba(16, 185, 129, 0.1)' }}
            >
              <div className="text-lg font-bold" style={{ color: 'var(--color-sentinel-green, #10B981)' }}>
                {recommendation.risk_level}
              </div>
              <div className="text-[10px]" style={{ color: 'var(--color-sentinel-text-secondary, #aaa)' }}>
                Risk Level
              </div>
            </div>
          </div>
        )}

        {/* Timestamp */}
        <div className="text-[10px]" style={{ color: 'var(--color-sentinel-text-disabled, #666)' }}>
          Detected at {new Date(recommendation.timestamp).toLocaleTimeString()} — Profile: {recommendation.profile}
        </div>
      </div>

      {/* Footer */}
      <div
        className="px-4 py-3 flex gap-2"
        style={{ borderTop: '1px solid var(--color-sentinel-border, #2a2a4a)' }}
      >
        <button
          onClick={() => { onApprove(recommendation.id); onClose(); }}
          className="flex-1 py-2 rounded text-sm font-medium flex items-center justify-center gap-1.5 transition-colors hover:brightness-110"
          style={{ background: 'var(--color-sentinel-green, #10B981)', color: '#fff' }}
        >
          <CheckCircle2 className="h-3.5 w-3.5" />
          Approve & Execute
        </button>
        <button
          onClick={onClose}
          className="px-4 py-2 rounded text-sm transition-colors hover:bg-white/10"
          style={{ color: 'var(--color-sentinel-text-secondary, #aaa)', border: '1px solid var(--color-sentinel-border, #2a2a4a)' }}
        >
          Dismiss
        </button>
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
    if (!siteId) return;
    const poll = async () => {
      try {
        const response = await fetch(`/api/recommendations/${siteId}`);
        const data = await response.json();
        const pending = data.recommendations?.filter((r: RecommendationData) => r.status?.toLowerCase() === 'pending') || [];
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
