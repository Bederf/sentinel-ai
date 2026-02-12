/**
 * Maintenance History Tabs Container
 *
 * Displays tabbed interface for work orders and alerts history.
 * Follows SENTINEL design patterns with Grafana-inspired styling.
 */

import { useState } from 'react';
import { WorkOrderHistoryList } from './WorkOrderHistoryList';
import { EquipmentAlertsList } from './EquipmentAlertsList';

interface MaintenanceHistoryTabsProps {
  equipmentId: string;
}

type TabType = 'work-orders' | 'alerts';

export function MaintenanceHistoryTabs({ equipmentId }: MaintenanceHistoryTabsProps) {
  const [activeTab, setActiveTab] = useState<TabType>('work-orders');

  const tabs: Array<{ id: TabType; label: string; icon: string }> = [
    { id: 'work-orders', label: 'Work Orders', icon: '🔧' },
    { id: 'alerts', label: 'Alerts & Errors', icon: '⚠️' },
  ];

  return (
    <div>
      {/* Tab Switcher */}
      <div
        className="flex gap-0 mb-4 border-b"
        style={{ borderColor: 'var(--color-grafana-border)' }}
      >
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className="px-4 py-2 text-sm font-medium transition-colors relative"
            style={{
              color: activeTab === tab.id
                ? 'var(--color-grafana-text-primary)'
                : 'var(--color-grafana-text-secondary)',
              borderBottom: activeTab === tab.id
                ? '2px solid var(--color-grafana-blue)'
                : 'none',
              marginBottom: activeTab === tab.id ? '-2px' : '0',
              background: 'transparent',
              cursor: 'pointer',
            }}
            onMouseEnter={(e) => {
              if (activeTab !== tab.id) {
                (e.target as HTMLElement).style.color = 'var(--color-grafana-text-primary)';
              }
            }}
            onMouseLeave={(e) => {
              if (activeTab !== tab.id) {
                (e.target as HTMLElement).style.color = 'var(--color-grafana-text-secondary)';
              }
            }}
          >
            <span className="mr-1">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div>
        {activeTab === 'work-orders' && (
          <WorkOrderHistoryList equipmentId={equipmentId} limit={10} />
        )}
        {activeTab === 'alerts' && (
          <EquipmentAlertsList equipmentId={equipmentId} limit={10} />
        )}
      </div>
    </div>
  );
}
