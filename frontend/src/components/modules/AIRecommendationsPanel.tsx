import { useState } from 'react';

import { useModules, useCriticalRecommendations, useCrossSystemRecommendations } from '../../contexts/ModuleHooks';
import { PRIORITY_COLORS, MODULE_COLORS } from '../../lib/moduleRegistry';
import type { AIRecommendation, ModuleType } from '../../lib/moduleRegistry';
import { phaseAllows } from '../../lib/onboardingPhase';
import type { OnboardingPhase } from '../../lib/onboardingPhase';
import { Panel } from '../Panel';
import { Badge } from '../Badge';

interface AIRecommendationsPanelProps {
  compact?: boolean;
  maxItems?: number;
  moduleFilter?: ModuleType;
  sitePhase?: OnboardingPhase | string;
}

export function AIRecommendationsPanel({
  compact = false,
  maxItems = 10,
  moduleFilter,
  sitePhase,
}: AIRecommendationsPanelProps) {
  const {
    recommendations,
    activeModules,
    acknowledgeRecommendation,
    resolveRecommendation,
  } = useModules();

  const criticalRecs = useCriticalRecommendations();
  const crossSystemRecs = useCrossSystemRecommendations();

  const [filter, setFilter] = useState<'all' | 'critical' | 'cross_system' | ModuleType>('all');

  let filteredRecs = recommendations.filter(r => !r.resolved);

  if (moduleFilter) {
    filteredRecs = filteredRecs.filter(
      r => r.source_module === moduleFilter || r.related_modules.includes(moduleFilter)
    );
  } else if (filter === 'critical') {
    filteredRecs = criticalRecs;
  } else if (filter === 'cross_system') {
    filteredRecs = crossSystemRecs;
  } else if (filter !== 'all') {
    filteredRecs = filteredRecs.filter(r => r.source_module === filter);
  }

  const displayRecs = filteredRecs.slice(0, maxItems);

  if (!phaseAllows(sitePhase, "recommendations_ui")) {
    return null;
  }

  if (compact) {
    const borderColor = criticalRecs.length > 0 ? 'var(--color-sentinel-red)' : 'var(--color-sentinel-blue)';
    return (
      <div
        className="rounded-lg p-4"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
          borderTop: `4px solid ${borderColor}`,
        }}
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium" style={{ color: 'var(--color-sentinel-text-primary)' }}>AI Recommendations</p>
            <p className="text-2xl font-bold" style={{ color: 'var(--color-sentinel-text-primary)' }}>{filteredRecs.length}</p>
            <p className="text-xs italic" style={{ color: 'var(--color-sentinel-text-disabled)' }}>AI-generated</p>
          </div>
          {criticalRecs.length > 0 && (
            <Badge style={{ background: 'rgba(220,38,38,0.15)', color: 'var(--color-sentinel-red)' }}>{criticalRecs.length} Critical</Badge>
          )}
          {crossSystemRecs.length > 0 && (
            <Badge style={{ background: 'rgba(147,51,234,0.15)', color: '#a78bfa' }}>{crossSystemRecs.length} Cross-System</Badge>
          )}
        </div>
        {displayRecs.length > 0 && (
          <div className="mt-3 space-y-2">
            {displayRecs.slice(0, 3).map(rec => (
              <div
                key={rec.recommendation_id}
                className={`p-2 rounded text-sm ${
                  rec.priority === 'critical' ? 'bg-red-50' :
                  rec.priority === 'high' ? 'bg-amber-50' :
                  'bg-gray-50'
                }`}
              >
                <p className="font-medium truncate">{rec.title}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <Panel>
      <div className="flex items-start justify-between px-4 pt-4">
        <div>
          <h2 className="text-lg font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>AI Recommendations</h2>
          <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            {activeModules.length} module(s) active
          </p>
          <p className="text-xs mt-0.5 italic" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
            AI-generated recommendations &middot; Review before acting
          </p>
        </div>
        <div className="flex gap-2">
          {criticalRecs.length > 0 && (
            <Badge style={{ background: 'rgba(220,38,38,0.15)', color: 'var(--color-sentinel-red)' }}>{criticalRecs.length} Critical</Badge>
          )}
          {crossSystemRecs.length > 0 && (
            <Badge style={{ background: 'rgba(147,51,234,0.15)', color: '#a78bfa' }}>{crossSystemRecs.length} Cross-System</Badge>
          )}
        </div>
      </div>

      {!moduleFilter && (
        <div className="px-4 pt-4">
          <select
            value={filter}
            onChange={(event) => setFilter(event.target.value as typeof filter)}
            className="w-full rounded-md appearance-none cursor-pointer px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-0"
            style={{
              background: "var(--color-grafana-bg-secondary)",
              border: "1px solid var(--color-grafana-border)",
              color: "var(--color-grafana-text-primary)",
              boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
              outline: "none",
            }}
            aria-label="Filter recommendations"
          >
            <option value="all">All Recommendations</option>
            <option value="critical">Critical Only</option>
            <option value="cross_system">Cross-System Only</option>
            {activeModules.map(m => (
              <option key={m.module_type} value={m.module_type}>
                {m.module_type.toUpperCase()} Module
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="px-4 pt-4 pb-4 space-y-3">
        {displayRecs.length === 0 ? (
          <p className="text-center py-4" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            No active recommendations
          </p>
        ) : (
          displayRecs.map(rec => (
            <RecommendationCard
              key={rec.recommendation_id}
              recommendation={rec}
              onAcknowledge={() => acknowledgeRecommendation(rec.recommendation_id)}
              onResolve={() => resolveRecommendation(rec.recommendation_id)}
            />
          ))
        )}
      </div>

      {filteredRecs.length > maxItems && (
        <p className="text-center pb-4 text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
          +{filteredRecs.length - maxItems} more recommendations
        </p>
      )}
    </Panel>
  );
}

interface RecommendationCardProps {
  recommendation: AIRecommendation;
  onAcknowledge: () => void;
  onResolve: () => void;
}

function RecommendationCard({ recommendation, onAcknowledge, onResolve }: RecommendationCardProps) {
  const priorityStyles: Record<string, string> = {
    critical: 'border-red-500 bg-red-50',
    high: 'border-amber-500 bg-amber-50',
    medium: 'border-blue-500 bg-blue-50',
    low: 'border-gray-300 bg-gray-50',
  };

  return (
    <div
      className={`p-3 rounded-lg border-l-4 ${priorityStyles[recommendation.priority] || priorityStyles.low}`}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <Badge className="text-[10px] px-1.5 py-0.5" style={{
              background: recommendation.source === 'health_alert' ? 'rgba(249,115,22,0.15)' : recommendation.source === 'ai_optimizer' ? 'rgba(14,165,233,0.15)' : 'rgba(14,165,233,0.15)',
              color: recommendation.source === 'health_alert' ? 'var(--color-sentinel-orange)' : recommendation.source === 'ai_optimizer' ? 'var(--color-sentinel-sky)' : 'var(--color-sentinel-sky)',
            }}>
              {recommendation.source === 'health_alert' ? 'Health Alert'
                : recommendation.source === 'ai_optimizer' ? 'AI Optimization'
                : recommendation.source === 'financial_roi' ? 'ROI'
                : 'AI'}
            </Badge>
            <Badge className="text-[10px] px-1.5 py-0.5" style={{ background: 'rgba(107,114,128,0.15)', color: 'var(--color-sentinel-text-secondary)' }}>
              {recommendation.source_module.toUpperCase()}
            </Badge>
            <Badge className="text-[10px] px-1.5 py-0.5" style={{
              background: recommendation.priority === 'critical' ? 'rgba(220,38,38,0.15)' : recommendation.priority === 'high' ? 'rgba(245,158,11,0.15)' : 'rgba(107,114,128,0.15)',
              color: recommendation.priority === 'critical' ? 'var(--color-sentinel-red)' : recommendation.priority === 'high' ? 'var(--color-sentinel-amber)' : 'var(--color-sentinel-text-secondary)',
            }}>
              {recommendation.priority}
            </Badge>
            {recommendation.recommendation_type === 'cross_system' && (
              <Badge className="text-[10px] px-1.5 py-0.5" style={{ background: 'rgba(147,51,234,0.15)', color: '#a78bfa' }}>Cross-System</Badge>
            )}
            {recommendation.auto_actionable && (
              <Badge className="text-[10px] px-1.5 py-0.5" style={{ background: 'rgba(16,185,129,0.15)', color: 'var(--color-sentinel-green)' }}>Auto</Badge>
            )}
          </div>
          <p className="font-medium" style={{ color: 'var(--color-sentinel-text-primary)' }}>{recommendation.title}</p>
          <p className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>{recommendation.description}</p>

          {recommendation.related_modules.length > 0 && (
            <div className="flex gap-1 mt-2">
              <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Related:</span>
              {recommendation.related_modules.map(m => (
                <Badge key={m} className="text-[10px] px-1.5 py-0.5" style={{ background: 'rgba(107,114,128,0.15)', color: 'var(--color-sentinel-text-secondary)' }}>{m}</Badge>
              ))}
            </div>
          )}

          <p className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
            Confidence: {((recommendation.confidence ?? 0) * 100).toFixed(0)}%
          </p>
        </div>

        <div className="flex flex-col gap-1 ml-2">
          {!recommendation.acknowledged && (
            <button
              onClick={onAcknowledge}
              className="px-2 py-1 text-xs rounded font-medium transition-colors"
              style={{
                background: 'var(--color-sentinel-bg-secondary)',
                color: 'var(--color-sentinel-text-primary)',
                border: '1px solid var(--color-sentinel-border)',
              }}
            >
              Ack
            </button>
          )}
          <button
            onClick={onResolve}
            className="px-2 py-1 text-xs rounded font-medium transition-colors"
            style={{
              background: 'rgba(16, 185, 129, 0.15)',
              color: 'var(--color-sentinel-green)',
              border: '1px solid rgba(16, 185, 129, 0.3)',
            }}
          >
            Resolve
          </button>
        </div>
      </div>

      <p className="text-xs mt-2" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
        {new Date(recommendation.timestamp).toLocaleString()}
      </p>
    </div>
  );
}

export default AIRecommendationsPanel;
