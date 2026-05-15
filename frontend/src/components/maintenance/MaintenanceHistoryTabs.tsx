/**
 * Maintenance History Display
 *
 * Shows work order history for equipment.
 * Alerts are displayed separately in "Alarm Frequency" section to avoid duplication.
 * Follows SENTINEL design patterns with Grafana-inspired styling.
 */

import { WorkOrderHistoryList } from './WorkOrderHistoryList';

interface MaintenanceHistoryTabsProps {
  equipmentId: string;
}

export function MaintenanceHistoryTabs({ equipmentId }: MaintenanceHistoryTabsProps) {
  return (
    <div>
      {/* Title */}
      <h3
        className="text-sm font-semibold mb-3"
        style={{ color: 'var(--color-grafana-text-primary)' }}
      >
        Service Record History
      </h3>

      {/* Work Order List */}
      <WorkOrderHistoryList equipmentId={equipmentId} limit={10} />
    </div>
  );
}
