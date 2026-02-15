import React, { useState, useEffect } from 'react';
import { Card, Title, Text, Badge, Button, Grid, Select, SelectItem } from '@tremor/react';
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

export const SafetyStatusPanel: React.FC<SafetyStatusPanelProps> = ({
  siteId,
  deviceType,
  autoRefresh = true,
  refreshInterval = 30000, // 30 seconds
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

      // First, get all devices
      const devices = await api.getDevices(siteId, deviceType);

      // Fetch safety status for each device
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

  // Initial fetch
  useEffect(() => {
    fetchSafetyStatuses();
  }, [siteId, deviceType]);

  // Auto-refresh
  useEffect(() => {
    if (!autoRefresh) return;

    const intervalId = setInterval(fetchSafetyStatuses, refreshInterval);
    return () => clearInterval(intervalId);
  }, [autoRefresh, refreshInterval, siteId, deviceType]);

  // Filter safety statuses
  const filteredStatuses = safetyStatuses.filter((status) => {
    if (filterStatus === 'all') return true;
    if (filterStatus === 'warning') return status.overall_status === 'warning';
    if (filterStatus === 'blocked') return status.overall_status === 'blocked';
    if (filterStatus === 'alarm') return status.overall_status === 'alarm';
    if (filterStatus === 'safe') return status.overall_status === 'safe';
    return true;
  });

  // Statistics
  const stats = {
    total: safetyStatuses.length,
    safe: safetyStatuses.filter(s => s.overall_status === 'safe').length,
    warning: safetyStatuses.filter(s => s.overall_status === 'warning').length,
    blocked: safetyStatuses.filter(s => s.overall_status === 'blocked').length,
    alarm: safetyStatuses.filter(s => s.overall_status === 'alarm').length,
    unknown: safetyStatuses.filter(s => s.overall_status === 'unknown').length,
  };

  // Format time
  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
  };

  if (loading && safetyStatuses.length === 0) {
    return (
      <Card className={className}>
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
      </Card>
    );
  }

  return (
    <Card className={className}>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <Title>Safety Status</Title>
          <Text className="mt-1">
            Real-time safety validation status for all devices
          </Text>
        </div>

        <div className="flex items-center gap-3">
          <Select
            value={filterStatus}
            onValueChange={setFilterStatus}
            className="min-w-[120px]"
          >
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="safe">Safe Only</SelectItem>
            <SelectItem value="warning">Warnings</SelectItem>
            <SelectItem value="blocked">Blocked</SelectItem>
            <SelectItem value="alarm">Alarms</SelectItem>
          </Select>

          <Button
            size="xs"
            variant="secondary"
            onClick={fetchSafetyStatuses}
            loading={loading}
          >
            Refresh
          </Button>
        </div>
      </div>

      {error ? (
        <div className="bg-red-50 border border-red-200 rounded-md p-4">
          <Text className="text-red-700">{error}</Text>
          <Button
            size="xs"
            variant="light"
            className="mt-2"
            onClick={fetchSafetyStatuses}
          >
            Retry
          </Button>
        </div>
      ) : (
        <>
          {/* Statistics */}
          <Grid className="grid grid-cols-5 gap-4 mb-6">
            <div className="text-center">
              <div className="text-2xl font-bold text-gray-900">{stats.total}</div>
              <Text className="text-gray-600">Total</Text>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">{stats.safe}</div>
              <Text className="text-gray-600">Safe</Text>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-yellow-600">{stats.warning}</div>
              <Text className="text-gray-600">Warning</Text>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-red-600">{stats.blocked}</div>
              <Text className="text-gray-600">Blocked</Text>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-orange-600">{stats.alarm}</div>
              <Text className="text-gray-600">Alarm</Text>
            </div>
          </Grid>

          {/* Device List */}
          <div className="space-y-4">
            {filteredStatuses.length === 0 ? (
              <div className="text-center py-8">
                <Text className="text-gray-500">
                  No devices match the current filter
                </Text>
              </div>
            ) : (
              filteredStatuses.map((status) => (
                <div
                  key={status.device_id}
                  className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors"
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
                        <Text className="font-semibold text-gray-900">
                          {status.device_name}
                        </Text>
                        <Text className="text-xs text-gray-500">
                          ID: {status.device_id}
                        </Text>
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <Badge
                        size="xs"
                        color={
                          status.overall_status === 'safe' ? 'green' :
                          status.overall_status === 'warning' ? 'yellow' :
                          status.overall_status === 'blocked' ? 'red' :
                          status.overall_status === 'alarm' ? 'orange' : 'gray'
                        }
                      >
                        {status.active_rule_count} rules
                      </Badge>
                      <Text className="text-xs text-gray-500">
                        {formatTime(status.last_check)}
                      </Text>
                    </div>
                  </div>

                  {/* Point Statuses */}
                  {Object.keys(status.point_statuses).length > 0 && (
                    <div className="mt-3 pt-3 border-t border-gray-100">
                      <Text className="text-sm font-medium text-gray-700 mb-2">
                        Point Status
                      </Text>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {Object.entries(status.point_statuses).map(([pointName, pointStatus]) => (
                          <div
                            key={pointName}
                            className="flex items-center justify-between p-2 bg-gray-50 rounded"
                          >
                            <div>
                              <Text className="text-sm font-medium text-gray-900">
                                {pointName}
                              </Text>
                              <Text className="text-xs text-gray-600">
                                Value: {String(pointStatus.value)}
                              </Text>
                            </div>
                            <div className="flex items-center gap-2">
                              {!pointStatus.allowed && (
                                <Badge size="xs" color="red">Blocked</Badge>
                              )}
                              {pointStatus.warnings.length > 0 && (
                                <Badge size="xs" color="yellow">
                                  {pointStatus.warnings.length} warning(s)
                                </Badge>
                              )}
                              {pointStatus.alarms.length > 0 && (
                                <Badge size="xs" color="orange">
                                  {pointStatus.alarms.length} alarm(s)
                                </Badge>
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

          {/* Footer */}
          <div className="mt-6 pt-4 border-t border-gray-200">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <Text className="text-sm text-gray-500">
                Showing {filteredStatuses.length} of {safetyStatuses.length} devices
              </Text>
              <Text className="text-sm text-gray-500">
                Last updated: {lastUpdated ? formatTime(lastUpdated) : 'Never'}
              </Text>
            </div>
          </div>
        </>
      )}
    </Card>
  );
};

// Compact version for dashboard
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
        // For compact version, just get a summary
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

  if (loading) {
    return (
      <Card className={className}>
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
      </Card>
    );
  }

  return (
    <Card className={className}>
      <Title className="mb-4">Safety Overview</Title>
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-6">
          <div className="text-center">
            <div className="text-3xl font-bold text-gray-900">{stats.total}</div>
            <Text className="text-gray-600">Devices</Text>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-center">
              <SafetyIndicator status="safe" size="lg" />
              <Text className="text-gray-600 mt-1">{stats.safe}</Text>
            </div>
            <div className="text-center">
              <SafetyIndicator status="warning" size="lg" />
              <Text className="text-gray-600 mt-1">{stats.warning}</Text>
            </div>
            <div className="text-center">
              <SafetyIndicator status="blocked" size="lg" />
              <Text className="text-gray-600 mt-1">{stats.blocked}</Text>
            </div>
            <div className="text-center">
              <SafetyIndicator status="alarm" size="lg" />
              <Text className="text-gray-600 mt-1">{stats.alarm}</Text>
            </div>
          </div>
        </div>

        <div className="text-right">
          <Text className="text-sm text-gray-500">
            {stats.blocked > 0 || stats.alarm > 0 ? (
              <span className="text-red-600 font-medium">
                Safety issues detected
              </span>
            ) : (
              <span className="text-green-600 font-medium">
                All systems safe
              </span>
            )}
          </Text>
          <Text className="text-xs text-gray-400 mt-1">
            Real-time monitoring
          </Text>
        </div>
      </div>
    </Card>
  );
};