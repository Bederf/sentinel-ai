/**
 * Integration Status Bar - Cross-Module Integration Indicator
 *
 * Shows which modules are active and their integration status.
 * Appears at the top of the dashboard when multiple modules are active.
 */


import { useModules } from '../../contexts/ModuleHooks';
import { MODULE_COLORS } from '../../lib/moduleRegistry';
import { useHealthThresholds } from '../../hooks/useHealthThresholds';

interface IntegrationStatusBarProps {
  compact?: boolean;
}

export function IntegrationStatusBar({ compact = false }: IntegrationStatusBarProps) {
  const { activeModules, integrationSummary } = useModules();
  const { thresholds } = useHealthThresholds();

  if (activeModules.length === 0) {
    return null;
  }

  const hasIntegrations = integrationSummary && integrationSummary.active_integrations.length > 0;

  const ModuleBadge = ({ label, bg, color, size }: { label: string; bg?: string; color?: string; size?: string }) => (
    <span className={`inline-flex items-center justify-center rounded font-medium whitespace-nowrap ${size === 'xs' ? 'text-xs px-2 py-0.5' : 'text-sm px-2.5 py-0.5'}`}
      style={{ background: bg || 'rgba(107, 114, 128, 0.15)', color: color || 'var(--color-sentinel-text-secondary)' }}>
      {label}
    </span>
  );

  if (compact) {
    return (
      <div className="flex items-center gap-2 px-3 py-1 bg-gray-50 rounded-full">
        {activeModules.map(m => (
          <ModuleBadge key={m.module_type} label={m.module_type.toUpperCase()} size="xs" />
        ))}
        {hasIntegrations && (
          <ModuleBadge label="Integrated" size="xs" />
        )}
      </div>
    );
  }

  return (
    <div className="bg-gradient-to-r from-gray-50 to-gray-100 border-b border-gray-200 px-4 py-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-gray-600">Active Modules:</span>
          <div className="flex gap-2">
            {activeModules.map(m => (
              <ModuleBadge key={m.module_type} label={m.module_type.toUpperCase() + (m.health_score < thresholds.healthy ? ` (${m.health_score.toFixed(0)}%)` : '')} />
            ))}
          </div>
        </div>

        {hasIntegrations && (
          <div className="flex items-center gap-2">
            <ModuleBadge label={`${integrationSummary!.active_integrations.length} Integration(s) Active`} />
            <span className="text-xs text-gray-500">
              {integrationSummary!.active_integrations.map(i => i.name).join(' | ')}
            </span>
          </div>
        )}

        {integrationSummary && integrationSummary.pending_recommendations > 0 && (
          <ModuleBadge label={`${integrationSummary.pending_recommendations} AI Recommendations`} />
        )}
      </div>
    </div>
  );
}

export default IntegrationStatusBar;
