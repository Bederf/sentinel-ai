/**
 * Work Order History List Component
 *
 * Displays work order history for equipment with status indicators and timestamps.
 * Follows SENTINEL Grafana-inspired design patterns.
 */

import { useEquipmentWorkOrders } from '@/hooks/useEquipmentHistory';
import { RefreshCw, Wrench, CheckCircle2, Clock, AlertCircle } from 'lucide-react';

interface WorkOrderHistoryListProps {
  equipmentId: string;
  limit?: number;
}

/**
 * Get relative time string from timestamp
 */
function getRelativeTime(timestamp: string): string {
  const now = new Date();
  const pastTime = new Date(timestamp);
  const diffMs = now.getTime() - pastTime.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) {
    return 'Just now';
  }
  if (diffMins < 60) {
    return `${diffMins}m ago`;
  }
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }
  return `${diffDays}d ago`;
}

/**
 * Get status color configuration
 */
function getStatusConfig(status: string): {
  color: string;
  bg: string;
  borderColor: string;
  label: string;
  icon?: React.ReactNode;
} {
  switch (status) {
    case 'completed':
      return {
        color: 'var(--color-status-success)',
        bg: 'rgba(115, 191, 105, 0.1)',
        borderColor: 'var(--color-status-success)',
        label: 'COMPLETED',
      };
    case 'in_progress':
      return {
        color: 'var(--color-grafana-blue)',
        bg: 'rgba(50, 116, 217, 0.1)',
        borderColor: 'var(--color-grafana-blue)',
        label: 'IN PROGRESS',
      };
    case 'assigned':
      return {
        color: 'var(--color-grafana-yellow)',
        bg: 'rgba(242, 204, 12, 0.1)',
        borderColor: 'var(--color-grafana-yellow)',
        label: 'ASSIGNED',
      };
    case 'scheduled':
      return {
        color: 'var(--color-grafana-text-secondary)',
        bg: 'rgba(142, 142, 142, 0.1)',
        borderColor: 'var(--color-grafana-text-secondary)',
        label: 'SCHEDULED',
      };
    case 'cancelled':
      return {
        color: 'var(--color-grafana-text-disabled)',
        bg: 'rgba(100, 100, 100, 0.1)',
        borderColor: 'var(--color-grafana-text-disabled)',
        label: 'CANCELLED',
      };
    default:
      return {
        color: 'var(--color-grafana-text-secondary)',
        bg: 'rgba(142, 142, 142, 0.1)',
        borderColor: 'var(--color-grafana-text-secondary)',
        label: status.toUpperCase(),
      };
  }
}

/**
 * Get priority color configuration
 */
function getPriorityConfig(priority: string): { color: string; label: string } {
  switch (priority) {
    case 'urgent':
      return { color: 'var(--color-status-error)', label: 'URGENT' };
    case 'high':
      return { color: 'var(--color-status-warning)', label: 'HIGH' };
    case 'medium':
      return { color: 'var(--color-grafana-yellow)', label: 'MEDIUM' };
    case 'low':
      return { color: 'var(--color-grafana-text-secondary)', label: 'LOW' };
    default:
      return { color: 'var(--color-grafana-text-secondary)', label: priority.toUpperCase() };
  }
}

export function WorkOrderHistoryList({ equipmentId, limit = 10 }: WorkOrderHistoryListProps) {
  const { data: workOrders = [], isLoading, error } = useEquipmentWorkOrders(equipmentId, limit);

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <RefreshCw
          className="h-5 w-5 animate-spin"
          style={{ color: 'var(--color-grafana-text-disabled)' }}
        />
        <span
          className="ml-2 text-sm"
          style={{ color: 'var(--color-grafana-text-secondary)' }}
        >
          Loading work orders...
        </span>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div
        className="p-3 rounded text-sm flex items-center gap-2"
        style={{
          background: 'rgba(242, 73, 92, 0.1)',
          border: '1px solid rgba(242, 73, 92, 0.3)',
          color: 'var(--color-status-error)',
        }}
      >
        <AlertCircle className="h-4 w-4 flex-shrink-0" />
        <span>Failed to load work orders</span>
      </div>
    );
  }

  // Empty state
  if (workOrders.length === 0) {
    return (
      <div className="text-center py-8">
        <CheckCircle2
          className="h-8 w-8 mx-auto mb-2"
          style={{ color: 'var(--color-status-success)' }}
        />
        <span
          className="text-sm block"
          style={{ color: 'var(--color-grafana-text-secondary)' }}
        >
          No service records found
        </span>
        <span
          className="text-xs block mt-1"
          style={{ color: 'var(--color-grafana-text-disabled)' }}
        >
          Equipment has clean service history
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {workOrders.map((workOrder) => {
        const statusConfig = getStatusConfig(workOrder.status);
        const priorityConfig = getPriorityConfig(workOrder.priority);

        return (
          <div
            key={workOrder.id}
            className="rounded overflow-hidden transition-colors hover:brightness-105"
            style={{
              background: 'var(--color-grafana-bg-secondary)',
              border: `1px solid ${statusConfig.borderColor}33`,
              borderLeft: `3px solid ${statusConfig.borderColor}`,
            }}
          >
            <div className="p-3">
              {/* Header: Title and Status Badge */}
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="flex items-start gap-2 flex-1 min-w-0">
                  <Wrench
                    className="h-4 w-4 mt-0.5 flex-shrink-0"
                    style={{ color: statusConfig.color }}
                  />
                  <div className="min-w-0 flex-1">
                    <h4
                      className="text-sm font-medium line-clamp-1"
                      style={{ color: 'var(--color-grafana-text-primary)' }}
                    >
                      {workOrder.title}
                    </h4>
                    {workOrder.code && (
                      <p
                        className="text-xs mt-0.5"
                        style={{ color: 'var(--color-grafana-text-disabled)' }}
                      >
                        {workOrder.code}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  <span
                    className="text-xs font-medium px-1.5 py-0.5 rounded"
                    style={{
                      background: `${priorityConfig.color}20`,
                      color: priorityConfig.color,
                    }}
                  >
                    {priorityConfig.label}
                  </span>
                  <span
                    className="text-xs font-medium px-1.5 py-0.5 rounded"
                    style={{
                      background: `${statusConfig.color}20`,
                      color: statusConfig.color,
                    }}
                  >
                    {statusConfig.label}
                  </span>
                </div>
              </div>

              {/* Details Row: Technician and Timestamp */}
              <div className="flex items-center justify-between gap-2 text-xs">
                {workOrder.technician_name || workOrder.assigned_to ? (
                  <span style={{ color: 'var(--color-grafana-text-secondary)' }}>
                    {workOrder.technician_name || workOrder.assigned_to}
                  </span>
                ) : (
                  <span style={{ color: 'var(--color-grafana-text-disabled)' }}>
                    Unassigned
                  </span>
                )}
                <div className="flex items-center gap-1">
                  <Clock
                    className="h-3 w-3"
                    style={{ color: 'var(--color-grafana-text-disabled)' }}
                  />
                  <span style={{ color: 'var(--color-grafana-text-disabled)' }}>
                    {getRelativeTime(workOrder.created_at)}
                  </span>
                </div>
              </div>

              {/* Description if available */}
              {workOrder.description && (
                <p
                  className="text-xs mt-2 line-clamp-2"
                  style={{ color: 'var(--color-grafana-text-secondary)' }}
                >
                  {workOrder.description}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
