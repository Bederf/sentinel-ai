/**
 * MonitoringKPIPanel — Phase 108
 *
 * Two-row, four-column grid of KPICard instances:
 * Row 1 (Ingestion): Freshness, Error Rate, Match Coverage, Unmatched Points
 * Row 2 (Control): Shadow Writes, Blocked Writes, Approved Writes, Safety Violations
 */

import { Clock, AlertTriangle, Target, Unlink, Ghost, ShieldOff, CheckCircle, ShieldAlert } from 'lucide-react';
import { KPICard } from '@/components/KPICard';
import type { IngestionKPIs, ControlKPIs } from '@/lib/api/system';

interface MonitoringKPIPanelProps {
  ingestion: IngestionKPIs;
  control: ControlKPIs;
}

export function MonitoringKPIPanel({ ingestion, control }: MonitoringKPIPanelProps) {
  return (
    <div className="space-y-4">
      {/* Row 1: Ingestion KPIs */}
      <div>
        <p
          className="text-xs uppercase tracking-wider font-medium mb-3"
          style={{ color: 'var(--color-sentinel-text-secondary)' }}
        >
          Ingestion Health
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KPICard
            title="Freshness"
            value={ingestion.freshness_hours < 9999 ? `${ingestion.freshness_hours.toFixed(1)}h` : 'N/A'}
            icon={<Clock className="w-4 h-4" />}
            accentColor={ingestion.freshness_hours <= 1 ? 'green' : ingestion.freshness_hours <= 24 ? 'orange' : 'red'}
            subtitle="Hours since sync"
          />
          <KPICard
            title="Error Rate"
            value={`${ingestion.error_rate.toFixed(1)}%`}
            icon={<AlertTriangle className="w-4 h-4" />}
            accentColor={ingestion.error_rate <= 5 ? 'green' : ingestion.error_rate <= 10 ? 'orange' : 'red'}
            subtitle="Sync failures (7d)"
          />
          <KPICard
            title="Match Coverage"
            value={`${ingestion.match_coverage.toFixed(0)}%`}
            icon={<Target className="w-4 h-4" />}
            accentColor={ingestion.match_coverage >= 90 ? 'green' : ingestion.match_coverage >= 50 ? 'orange' : 'red'}
            subtitle="Points matched"
          />
          <KPICard
            title="Unmatched"
            value={ingestion.unmatched_points}
            icon={<Unlink className="w-4 h-4" />}
            accentColor={ingestion.unmatched_points === 0 ? 'green' : 'orange'}
            subtitle={`of ${ingestion.total_points} total`}
          />
        </div>
      </div>

      {/* Row 2: Control KPIs */}
      <div>
        <p
          className="text-xs uppercase tracking-wider font-medium mb-3"
          style={{ color: 'var(--color-sentinel-text-secondary)' }}
        >
          Control Activity (24h)
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KPICard
            title="Shadow Writes"
            value={control.shadow_writes_24h}
            icon={<Ghost className="w-4 h-4" />}
            accentColor="purple"
            subtitle="Logged, not executed"
          />
          <KPICard
            title="Blocked"
            value={control.blocked_writes_24h}
            icon={<ShieldOff className="w-4 h-4" />}
            accentColor={control.blocked_writes_24h === 0 ? 'green' : 'red'}
            subtitle="Safety rejected"
          />
          <KPICard
            title="Approved"
            value={control.approved_writes_24h}
            icon={<CheckCircle className="w-4 h-4" />}
            accentColor="green"
            subtitle="Successfully executed"
          />
          <KPICard
            title="Safety Violations"
            value={control.safety_violations_24h}
            icon={<ShieldAlert className="w-4 h-4" />}
            accentColor={control.safety_violations_24h === 0 ? 'green' : 'red'}
            subtitle="Validation failures"
          />
        </div>
      </div>
    </div>
  );
}

export default MonitoringKPIPanel;
