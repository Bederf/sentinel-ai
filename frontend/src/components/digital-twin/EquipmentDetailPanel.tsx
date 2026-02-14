import { useState } from 'react';
import type { Equipment } from '@/lib/api/sites';

interface EquipmentDetailPanelProps {
  equipment: Equipment;
  onClose: () => void;
}

export function EquipmentDetailPanel({ equipment, onClose }: EquipmentDetailPanelProps) {
  const [activeTab, setActiveTab] = useState<'live' | 'controls' | 'alerts' | 'maintenance'>('live');

  const getStatusBadgeColor = (equipment: Equipment) => {
    const status = equipment.status?.toLowerCase() || 'offline';
    const health = (equipment as any).health_score || 0;

    if (status === 'fault' || health < 30) return 'bg-red-900/30 text-red-400 border-red-700';
    if (status === 'warning' || health < 60) return 'bg-yellow-900/30 text-yellow-400 border-yellow-700';
    if (status === 'online' || health >= 60) return 'bg-green-900/30 text-green-400 border-green-700';
    return 'bg-gray-700/30 text-gray-400 border-gray-600';
  };

  const getHealthScore = () => {
    return (equipment as any).health_score || Math.random() * 100;
  };

  const healthScore = getHealthScore();

  return (
    <div
      className="h-full w-full flex flex-col matrix-panel"
      style={{
        background: 'rgba(6, 14, 24, 0.95)',
        borderRadius: 0,
      }}
    >
      {/* Header */}
      <div
        className="flex-none p-4 flex justify-between items-start"
        style={{ borderBottom: '1px solid var(--color-sentinel-border)' }}
      >
        <div className="flex-1 pr-3">
          <h2 className="text-lg font-bold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
            {equipment.name || (equipment as any).code}
          </h2>
          <p className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
            {(equipment as any).code}
          </p>
          <div className="flex gap-2 mt-2">
            <span
              className={`text-xs px-2 py-1 rounded border ${getStatusBadgeColor(equipment)}`}
            >
              {equipment.status || 'Offline'}
            </span>
            <span
              className="text-xs px-2 py-1 rounded border"
              style={{
                background: `rgba(${Math.round((100 - healthScore) / 100 * 255)}, ${Math.round(healthScore / 100 * 255)}, 0, 0.15)`,
                color: healthScore < 60 ? '#f59e0b' : '#10b981',
                borderColor: healthScore < 60 ? 'rgba(245, 158, 11, 0.3)' : 'rgba(16, 185, 129, 0.3)',
              }}
            >
              Health: {Math.round(healthScore)}%
            </span>
          </div>
        </div>
        <button
          onClick={onClose}
          className="matrix-btn flex-none px-2 py-1"
          style={{
            fontSize: '16px',
            minWidth: 'auto',
            padding: '4px 8px',
          }}
          aria-label="Close"
        >
          ✕
        </button>
      </div>

      {/* Tabs */}
      <div
        className="flex-none flex border-b"
        style={{ borderColor: 'rgba(0, 255, 65, 0.2)' }}
      >
        {(['live', 'controls', 'alerts', 'maintenance'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className="flex-1 px-3 py-2 text-xs font-medium uppercase tracking-widest transition-colors border-b-2 -mb-px"
            style={{
              fontFamily: 'Orbitron, monospace',
              color:
                activeTab === tab
                  ? '#00FF41'
                  : 'rgba(0, 255, 65, 0.4)',
              borderColor: activeTab === tab ? '#00FF41' : 'transparent',
              background:
                activeTab === tab
                  ? 'rgba(0, 255, 65, 0.08)'
                  : 'transparent',
              textShadow: activeTab === tab ? '0 0 8px rgba(0, 255, 65, 0.4)' : 'none',
            }}
          >
            {tab === 'live' && 'LIVE'}
            {tab === 'controls' && 'CTRL'}
            {tab === 'alerts' && 'ALERTS'}
            {tab === 'maintenance' && 'SVC'}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {activeTab === 'live' && (
          <div className="space-y-4">
            {/* Zone & Desk Info for DALI Sensors */}
            {((equipment as any).equipment_type || 'unknown').toLowerCase() === 'dali' && (
              <div
                className="p-3"
                style={{
                  background: 'rgba(0, 255, 65, 0.08)',
                  border: '1px solid rgba(0, 255, 65, 0.3)',
                  boxShadow: '0 0 8px rgba(0, 255, 65, 0.2)',
                }}
              >
                <div className="text-xs font-medium mb-2" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                  Zone & Occupancy
                </div>
                <div className="space-y-2">
                  <div>
                    <div className="text-xs" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
                      Zone
                    </div>
                    <div className="text-sm font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                      {(() => {
                        const deviceInfo = (equipment as any).device_info || {};
                        return deviceInfo.zone_id || 'Unassigned';
                      })()}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
                      Associated Desks
                    </div>
                    <div className="text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                      ~20 desks per zone
                    </div>
                  </div>
                  <div>
                    <div className="text-xs" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
                      Occupancy
                    </div>
                    <div className="text-lg font-bold" style={{ color: 'var(--color-sentinel-accent)' }}>
                      {Math.random() > 0.5 ? 'Occupied' : 'Vacant'}
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div
              className="p-3"
              style={{
                background: 'rgba(0, 255, 65, 0.08)',
                border: '1px solid rgba(0, 255, 65, 0.3)',
                boxShadow: '0 0 8px rgba(0, 255, 65, 0.2)',
              }}
            >
              <div className="text-xs font-medium mb-2" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Temperature
              </div>
              <div className="text-2xl font-bold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                {(Math.random() * 10 + 18).toFixed(1)}°C
              </div>
              <div className="text-xs mt-2" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
                Setpoint: 22°C
              </div>
            </div>

            <div
              className="p-3"
              style={{
                background: 'rgba(0, 255, 65, 0.08)',
                border: '1px solid rgba(0, 255, 65, 0.3)',
                boxShadow: '0 0 8px rgba(0, 255, 65, 0.2)',
              }}
            >
              <div className="text-xs font-medium mb-2" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Energy Usage
              </div>
              <div className="text-2xl font-bold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                {(Math.random() * 5000 + 2000).toFixed(0)} W
              </div>
              <div className="text-xs mt-2" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
                Daily: {(Math.random() * 80 + 40).toFixed(1)} kWh
              </div>
            </div>

            <div
              className="p-3"
              style={{
                background: 'rgba(0, 255, 65, 0.08)',
                border: '1px solid rgba(0, 255, 65, 0.3)',
                boxShadow: '0 0 8px rgba(0, 255, 65, 0.2)',
              }}
            >
              <div className="text-xs font-medium mb-2" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Equipment Type
              </div>
              <div className="text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                {(equipment as any).equipment_type || 'Unknown'}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'controls' && (
          <div className="space-y-4">
            <div
              className="p-3"
              style={{
                background: 'rgba(0, 255, 65, 0.08)',
                border: '1px solid rgba(0, 255, 65, 0.3)',
                boxShadow: '0 0 8px rgba(0, 255, 65, 0.2)',
              }}
            >
              <div className="text-xs font-medium mb-3" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Mode
              </div>
              <div className="flex gap-2">
                <button
                  className="flex-1 px-3 py-2 text-xs rounded transition-colors"
                  style={{
                    background: 'var(--color-sentinel-accent)',
                    color: 'white',
                  }}
                >
                  Auto
                </button>
                <button
                  className="flex-1 px-3 py-2 text-xs rounded transition-colors"
                  style={{
                    background: 'var(--color-sentinel-bg-secondary)',
                    color: 'var(--color-sentinel-text-secondary)',
                    border: '1px solid var(--color-sentinel-border)',
                  }}
                >
                  Manual
                </button>
              </div>
            </div>

            <div
              className="p-3"
              style={{
                background: 'rgba(0, 255, 65, 0.08)',
                border: '1px solid rgba(0, 255, 65, 0.3)',
                boxShadow: '0 0 8px rgba(0, 255, 65, 0.2)',
              }}
            >
              <div className="text-xs font-medium mb-3" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Setpoint
              </div>
              <input
                type="range"
                min="16"
                max="28"
                defaultValue="22"
                className="w-full"
                style={{ cursor: 'pointer' }}
              />
              <div className="text-sm mt-2" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                22°C
              </div>
            </div>
          </div>
        )}

        {activeTab === 'alerts' && (
          <div className="space-y-3">
            <div
              className="p-3 rounded border-l-2"
              style={{
                background: 'rgba(34, 197, 94, 0.1)',
                borderColor: '#22c55e',
              }}
            >
              <div className="text-xs font-medium" style={{ color: '#22c55e' }}>
                ✓ Online
              </div>
              <div className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Device is operational
              </div>
            </div>

            <div
              className="p-3 rounded border-l-2"
              style={{
                background: 'rgba(59, 130, 246, 0.1)',
                borderColor: '#3b82f6',
              }}
            >
              <div className="text-xs font-medium" style={{ color: '#3b82f6' }}>
                ⓘ Maintenance Due
              </div>
              <div className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Scheduled service in 30 days
              </div>
            </div>
          </div>
        )}

        {activeTab === 'maintenance' && (
          <div className="space-y-3">
            <div
              className="p-3"
              style={{
                background: 'rgba(0, 255, 65, 0.08)',
                border: '1px solid rgba(0, 255, 65, 0.3)',
                boxShadow: '0 0 8px rgba(0, 255, 65, 0.2)',
              }}
            >
              <div className="text-xs font-medium mb-2" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Last Service
              </div>
              <div className="text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                2024-12-15
              </div>
              <div className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
                By: Technician Team A
              </div>
            </div>

            <div
              className="p-3"
              style={{
                background: 'rgba(0, 255, 65, 0.08)',
                border: '1px solid rgba(0, 255, 65, 0.3)',
                boxShadow: '0 0 8px rgba(0, 255, 65, 0.2)',
              }}
            >
              <div className="text-xs font-medium mb-2" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Service Hours
              </div>
              <div className="text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                {(Math.random() * 5000 + 10000).toFixed(0)} hours
              </div>
            </div>

            <button
              className="w-full px-4 py-2 rounded text-sm font-medium transition-colors"
              style={{
                background: 'var(--color-sentinel-accent)',
                color: 'white',
              }}
            >
              Raise Work Order
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
