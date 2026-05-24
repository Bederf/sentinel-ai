import React, { useState, useEffect } from 'react';

import { SafetyIndicator } from './SafetyIndicator';
import type { SafetyStatus } from './SafetyIndicator';
import api from '@/lib/api';
import type { DeviceSafetyStatus } from '@/lib/api';

interface SafetyStatusPanelProps {
  siteId?: string;
  deviceType?: string;
  autoRefresh?: boolean;
  refreshInterval?: number;
  className?: string;
}

const badgeColors: Record<string, { bg: string; color: string }> = {
  safe: { bg: "rgba(16,185,129,0.15)", color: "var(--color-sentinel-green)" },
  warning: { bg: "rgba(245,158,11,0.15)", color: "var(--color-sentinel-amber)" },
  blocked: { bg: "rgba(220,38,38,0.15)", color: "var(--color-sentinel-red)" },
  alarm: { bg: "rgba(249,115,22,0.15)", color: "#fb923c" },
  unknown: { bg: "rgba(142,142,142,0.15)", color: "var(--color-sentinel-text-secondary)" },
  green: { bg: "rgba(16,185,129,0.15)", color: "var(--color-sentinel-green)" },
  yellow: { bg: "rgba(245,158,11,0.15)", color: "var(--color-sentinel-amber)" },
  red: { bg: "rgba(220,38,38,0.15)", color: "var(--color-sentinel-red)" },
  orange: { bg: "rgba(249,115,22,0.15)", color: "#fb923c" },
  gray: { bg: "rgba(142,142,142,0.15)", color: "var(--color-sentinel-text-secondary)" },
};

function SentinelBadge({ color, size = "xs", children }: { color: string; size?: string; children: React.ReactNode }) {
  const c = badgeColors[color] || badgeColors.gray;
  const sizeClass = size === "lg" ? "px-3 py-1 text-sm" : size === "sm" ? "px-2 py-0.5 text-xs" : "px-1.5 py-0.5 text-xs";
  return (
    <span className={`inline-flex items-center font-medium rounded-full ${sizeClass}`} style={{ background: c.bg, color: c.color }}>
      {children}
    </span>
  );
}

export const SafetyStatusPanel: React.FC<SafetyStatusPanelProps> = ({
  siteId,
  deviceType,
  autoRefresh = true,
  refreshInterval = 30000,
  className = '',
}) => {
  const [safetyStatuses, setSafetyStatuses] = useState<DeviceSafetyStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [lastUpdated, setLastUpdated] = useState<string>('');

  const fetchSafetyStatuses = async () => {
    try {
      setLoading(true);
      setError(null);

      const devices = await api.getDevices(siteId, deviceType);

      const statusPromises = devices.map(async (device) => {
        try {
          const status = await api.getDeviceFullSafetyStatus(device.id);
          return status;
        } catch (err) {
          console.error(`Failed to fetch safety status for device ${device.id}:`, err);
          return {
            device_id: device.id,
            device_name: device.name,
            overall_status: 'unknown' as SafetyStatus,
            point_statuses: {},
            active_rule_count: 0,
            last_check: new Date().toISOString(),
          };
        }
      });

      const statuses = await Promise.all(statusPromises);
      setSafetyStatuses(statuses);
      setLastUpdated(new Date().toISOString());
    } catch (err) {
      console.error('Failed to fetch safety statuses:', err);
      setError('Failed to load safety status data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSafetyStatuses();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId, deviceType]);

  useEffect(() => {
    if (!autoRefresh) return;

    const intervalId = setInterval(fetchSafetyStatuses, refreshInterval);
    return () => clearInterval(intervalId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, refreshInterval, siteId, deviceType]);

  const filteredStatuses = safetyStatuses.filter((status) => {
    if (filterStatus === 'all') return true;
    if (filterStatus === 'warning') return status.overall_status === 'warning';
    if (filterStatus === 'blocked') return status.overall_status === 'blocked';
    if (filterStatus === 'alarm') return status.overall_status === 'alarm';
    if (filterStatus === 'safe') return status.overall_status === 'safe';
    return true;
  });

  const stats = {
    total: safetyStatuses.length,
    safe: safetyStatuses.filter(s => s.overall_status === 'safe').length,
    warning: safetyStatuses.filter(s => s.overall_status === 'warning').length,
    blocked: safetyStatuses.filter(s => s.overall_status === 'blocked').length,
    alarm: safetyStatuses.filter(s => s.overall_status === 'alarm').length,
    unknown: safetyStatuses.filter(s => s.overall_status === 'unknown').length,
  };

  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
  };

  const cardStyle: React.CSSProperties = {
    background: "var(--color-sentinel-bg-panel)",
    border: "1px solid var(--color-sentinel-border)",
    borderRadius: 8,
    padding: 16,
  };

  if (loading && safetyStatuses.length === 0) {
    return (
      <div className={className} style={cardStyle}>
        <div className="animate-pulse">
          <div
            className="h-6 rounded w-1/3 mb-4"
            style={{ background: "var(--color-sentinel-bg-secondary)" }}
          />
          <div className="space-y-3">
            <div
              className="h-4 rounded"
              style={{ background: "var(--color-sentinel-bg-secondary)" }}
            />
            <div
              className="h-4 rounded"
              style={{ background: "var(--color-sentinel-bg-secondary)" }}
            />
            <div
              className="h-4 rounded"
              style={{ background: "var(--color-sentinel-bg-secondary)" }}
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={className} style={cardStyle}>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h3 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Safety Status</h3>
          <p className="mt-1 text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Real-time safety validation status for all devices
          </p>
        </div>

        <div className="flex items-center gap-3">
          <select
            value={filterStatus}
            onChange={(event) => setFilterStatus(event.target.value)}
            className="min-w-[120px] rounded-md appearance-none cursor-pointer px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-0"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
              boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
              outline: "none",
            }}
            aria-label="Filter safety status"
          >
            <option value="all">All Status</option>
            <option value="safe">Safe Only</option>
            <option value="warning">Warnings</option>
            <option value="blocked">Blocked</option>
            <option value="alarm">Alarms</option>
          </select>

          <button
            onClick={fetchSafetyStatuses}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-md transition-colors disabled:opacity-50"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          >
            {loading && <div className="animate-spin h-3 w-3 border-2 border-current border-t-transparent rounded-full" />}
            Refresh
          </button>
        </div>
      </div>

      {error ? (
        <div className="rounded-md p-4" style={{ background: "rgba(220,38,38,0.15)", border: "1px solid rgba(220,38,38,0.3)" }}>
          <p style={{ color: "var(--color-sentinel-red)" }}>{error}</p>
          <button
            onClick={fetchSafetyStatuses}
            className="mt-2 inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-md transition-colors"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          >
            Retry
          </button>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-5 gap-4 mb-6">
            <div className="text-center">
              <div className="text-2xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>{stats.total}</div>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Total</p>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold" style={{ color: "var(--color-sentinel-green)" }}>{stats.safe}</div>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Safe</p>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold" style={{ color: "var(--color-sentinel-amber)" }}>{stats.warning}</div>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Warning</p>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold" style={{ color: "var(--color-sentinel-red)" }}>{stats.blocked}</div>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Blocked</p>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold" style={{ color: "#fb923c" }}>{stats.alarm}</div>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Alarm</p>
            </div>
          </div>

          <div className="space-y-4">
            {filteredStatuses.length === 0 ? (
              <div className="text-center py-8">
                <p style={{ color: "var(--color-sentinel-text-disabled)" }}>
                  No devices match the current filter
                </p>
              </div>
            ) : (
              filteredStatuses.map((status) => (
                <div
                  key={status.device_id}
                  className="border rounded-lg p-4 transition-colors"
                  style={{
                    borderColor: "var(--color-sentinel-border)",
                    background: "var(--color-sentinel-bg-panel)",
                  }}
                >
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <SafetyIndicator
                        status={status.overall_status}
                        deviceId={status.device_id}
                        deviceName={status.device_name}
                        size="md"
                        showLabel
                      />
                      <div>
                        <p className="font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                          {status.device_name}
                        </p>
                        <p className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                          ID: {status.device_id}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <SentinelBadge color={
                        status.overall_status === 'safe' ? 'green' :
                        status.overall_status === 'warning' ? 'yellow' :
                        status.overall_status === 'blocked' ? 'red' :
                        status.overall_status === 'alarm' ? 'orange' : 'gray'
                      } size="xs">
                        {status.active_rule_count} rules
                      </SentinelBadge>
                      <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                        {formatTime(status.last_check)}
                      </span>
                    </div>
                  </div>

                  {Object.keys(status.point_statuses).length > 0 && (
                    <div className="mt-3 pt-3 border-t" style={{ borderColor: "var(--color-sentinel-border)" }}>
                      <p className="text-sm font-medium mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
                        Point Status
                      </p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {Object.entries(status.point_statuses).map(([pointName, pointStatus]) => (
                          <div
                            key={pointName}
                            className="flex items-center justify-between p-2 rounded"
                            style={{ background: "var(--color-sentinel-bg-secondary)" }}
                          >
                            <div>
                              <p className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                                {pointName}
                              </p>
                              <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                                Value: {String(pointStatus.value)}
                              </p>
                            </div>
                            <div className="flex items-center gap-2">
                              {!pointStatus.allowed && (
                                <SentinelBadge color="red" size="xs">Blocked</SentinelBadge>
                              )}
                              {pointStatus.warnings.length > 0 && (
                                <SentinelBadge color="yellow" size="xs">
                                  {pointStatus.warnings.length} warning(s)
                                </SentinelBadge>
                              )}
                              {pointStatus.alarms.length > 0 && (
                                <SentinelBadge color="orange" size="xs">
                                  {pointStatus.alarms.length} alarm(s)
                                </SentinelBadge>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>

          <div className="mt-6 pt-4 border-t" style={{ borderColor: "var(--color-sentinel-border)" }}>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                Showing {filteredStatuses.length} of {safetyStatuses.length} devices
              </p>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                Last updated: {lastUpdated ? formatTime(lastUpdated) : 'Never'}
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

interface CompactSafetyStatusProps {
  className?: string;
}

export const CompactSafetyStatus: React.FC<CompactSafetyStatusProps> = ({ className = '' }) => {
  const [stats, setStats] = useState({
    total: 0,
    safe: 0,
    warning: 0,
    blocked: 0,
    alarm: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const devices = await api.getDevices();
        const statusPromises = devices.slice(0, 10).map(async (device) => {
          try {
            const status = await api.getDeviceFullSafetyStatus(device.id);
            return status.overall_status;
          } catch {
            return 'unknown' as SafetyStatus;
          }
        });

        const statuses = await Promise.all(statusPromises);

        setStats({
          total: devices.length,
          safe: statuses.filter(s => s === 'safe').length,
          warning: statuses.filter(s => s === 'warning').length,
          blocked: statuses.filter(s => s === 'blocked').length,
          alarm: statuses.filter(s => s === 'alarm').length,
        });
      } catch (err) {
        console.error('Failed to fetch safety stats:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchStats();
  }, []);

  const cardStyle: React.CSSProperties = {
    background: "var(--color-sentinel-bg-panel)",
    border: "1px solid var(--color-sentinel-border)",
    borderRadius: 8,
    padding: 16,
  };

  if (loading) {
    return (
      <div className={className} style={cardStyle}>
        <div className="animate-pulse">
          <div
            className="h-4 rounded w-1/2 mb-4"
            style={{ background: "var(--color-sentinel-bg-secondary)" }}
          />
          <div className="flex gap-4">
            <div
              className="h-8 rounded flex-1"
              style={{ background: "var(--color-sentinel-bg-secondary)" }}
            />
            <div
              className="h-8 rounded flex-1"
              style={{ background: "var(--color-sentinel-bg-secondary)" }}
            />
            <div
              className="h-8 rounded flex-1"
              style={{ background: "var(--color-sentinel-bg-secondary)" }}
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={className} style={cardStyle}>
      <h3 className="text-lg font-semibold mb-4" style={{ color: "var(--color-sentinel-text-primary)" }}>Safety Overview</h3>
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-6">
          <div className="text-center">
            <div className="text-3xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>{stats.total}</div>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Devices</p>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-center">
              <SafetyIndicator status="safe" size="lg" />
              <p className="text-sm mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>{stats.safe}</p>
            </div>
            <div className="text-center">
              <SafetyIndicator status="warning" size="lg" />
              <p className="text-sm mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>{stats.warning}</p>
            </div>
            <div className="text-center">
              <SafetyIndicator status="blocked" size="lg" />
              <p className="text-sm mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>{stats.blocked}</p>
            </div>
            <div className="text-center">
              <SafetyIndicator status="alarm" size="lg" />
              <p className="text-sm mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>{stats.alarm}</p>
            </div>
          </div>
        </div>

        <div className="text-right">
          <p className="text-sm" style={{ color: "var(--color-sentinel-text-disabled)" }}>
            {stats.blocked > 0 || stats.alarm > 0 ? (
              <span style={{ color: "var(--color-sentinel-red)" }}>
                Safety issues detected
              </span>
            ) : (
              <span style={{ color: "var(--color-sentinel-green)" }}>
                All systems safe
              </span>
            )}
          </p>
          <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>
            Real-time monitoring
          </p>
        </div>
      </div>
    </div>
  );
};
