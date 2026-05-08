/**
 * StatusBadge — central status vocabulary for SENTINEL.
 *
 * All status colors live here. Consumers pass a StatusKey; the label
 * defaults to the key with underscores replaced by spaces. Override with
 * the label prop when the API value differs from the display string.
 *
 * Call-site mapping rule: if an API returns a value not in StatusKey
 * (e.g. 'expiring_soon'), normalise it at the call site — do not add
 * aliases here.
 */

import React from 'react';
import { Badge } from './Badge';

export type StatusKey =
  // Compliance workflow
  | 'compliant' | 'non_compliant' | 'overdue' | 'expiring' | 'pending'
  // SLA status
  | 'met' | 'at_risk' | 'breached'
  // Contract lifecycle
  | 'active' | 'expired' | 'draft' | 'terminated'
  // Profitability
  | 'profitable' | 'break_even' | 'loss_making'
  // Action / task lifecycle
  | 'completed' | 'failed' | 'queued'
  // Zone occupancy
  | 'empty' | 'normal' | 'crowded' | 'over_capacity'
  // System state
  | 'online'
  // Alert severity
  | 'critical' | 'warning'
  // Risk level
  | 'high_risk';

interface StatusConfig {
  color: string;
  bg: string;
  bdr: string;
}

const G = { color: '#10B981', bg: 'rgba(16,185,129,0.12)',  bdr: 'rgba(16,185,129,0.3)' };
const A = { color: '#F59E0B', bg: 'rgba(245,158,11,0.12)',  bdr: 'rgba(245,158,11,0.3)' };
const R = { color: '#DC2626', bg: 'rgba(220,38,38,0.12)',   bdr: 'rgba(220,38,38,0.3)' };
const B = { color: '#3B82F6', bg: 'rgba(59,130,246,0.12)',  bdr: 'rgba(59,130,246,0.3)' };
const N = { color: '#8B8B8B', bg: 'rgba(142,142,142,0.12)', bdr: 'rgba(142,142,142,0.3)' };
const P = { color: '#8B5CF6', bg: 'rgba(139,92,246,0.12)',  bdr: 'rgba(139,92,246,0.3)' };

const STATUS_CONFIG: Record<StatusKey, StatusConfig> = {
  // Compliance
  compliant:     G,
  non_compliant: R,
  overdue:       R,
  expiring:      A,
  pending:       P,
  // SLA
  met:           G,
  at_risk:       A,
  breached:      R,
  // Contract lifecycle
  active:        G,
  expired:       R,
  draft:         N,
  terminated:    R,
  // Profitability
  profitable:    G,
  break_even:    A,
  loss_making:   R,
  // Action / task lifecycle
  completed:     G,
  failed:        R,
  queued:        A,
  // Zone occupancy
  empty:         G,
  normal:        B,
  crowded:       A,
  over_capacity: R,
  // System state
  online:        G,
  // Alert severity
  critical:      R,
  warning:       A,
  // Risk level
  high_risk:     R,
};

interface StatusBadgeProps {
  status: StatusKey;
  label?: string;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  label,
  className = '',
}) => {
  const cfg = STATUS_CONFIG[status];
  return (
    <Badge
      className={className}
      style={{
        color: cfg.color,
        background: cfg.bg,
        border: `1px solid ${cfg.bdr}`,
      }}
    >
      {label ?? status.replace(/_/g, ' ')}
    </Badge>
  );
};

export default StatusBadge;
