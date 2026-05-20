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

/* All colors reference CSS design tokens — theme switching Just Works */
const G: StatusConfig = { color: 'var(--color-sentinel-green)',  bg: 'color-mix(in oklch, var(--color-sentinel-green) 12%, transparent)',  bdr: 'color-mix(in oklch, var(--color-sentinel-green) 30%, transparent)' };
const A: StatusConfig = { color: 'var(--color-sentinel-amber)', bg: 'color-mix(in oklch, var(--color-sentinel-amber) 12%, transparent)', bdr: 'color-mix(in oklch, var(--color-sentinel-amber) 30%, transparent)' };
const R: StatusConfig = { color: 'var(--color-sentinel-red)',   bg: 'color-mix(in oklch, var(--color-sentinel-red) 12%, transparent)',   bdr: 'color-mix(in oklch, var(--color-sentinel-red) 30%, transparent)' };
const B: StatusConfig = { color: 'var(--color-sentinel-blue)',  bg: 'color-mix(in oklch, var(--color-sentinel-blue) 12%, transparent)',  bdr: 'color-mix(in oklch, var(--color-sentinel-blue) 30%, transparent)' };
const N: StatusConfig = { color: 'var(--color-sentinel-text-disabled)', bg: 'color-mix(in oklch, var(--color-sentinel-text-disabled) 12%, transparent)', bdr: 'color-mix(in oklch, var(--color-sentinel-text-disabled) 30%, transparent)' };
const P: StatusConfig = { color: 'var(--color-sentinel-purple)', bg: 'color-mix(in oklch, var(--color-sentinel-purple) 12%, transparent)', bdr: 'color-mix(in oklch, var(--color-sentinel-purple) 30%, transparent)' };

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
