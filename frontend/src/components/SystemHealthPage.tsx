/**
 * System Health & Diagnostics Dashboard
 * 
 * Three-tab interface for monitoring system health:
 * 1. Realtime Status - Unified health overview with component cards
 * 2. Historical Insights - Uptime metrics and health trends over 24h/7d/30d
 * 3. Diagnostics - SIMBIOT diagnostic results and error logs
 */

import React, { useState, useEffect } from 'react';
import { RefreshCw, AlertCircle } from 'lucide-react';
import { TabGroup, TabList, Tab, TabPanels, TabPanel } from '@tremor/react';
import { systemApi, type SystemHealthSnapshot } from '@/lib/api/system';

import { HealthOverviewHeader } from './system/HealthOverviewHeader';
import { BMSConnectivityCard } from './system/BMSConnectivityCard';
import { APIHealthCard } from './system/APIHealthCard';
import { DataFreshnessCard } from './system/DataFreshnessCard';
import { DatabaseStatusCard } from './system/DatabaseStatusCard';
import { ServiceHealthCard } from './system/ServiceHealthCard';
import { UptimeMetricsCard } from './system/UptimeMetricsCard';
import { HealthTrendChart } from './system/HealthTrendChart';
import { DiagnosticsControls } from './system/DiagnosticsControls';
import { DiagnosticsResults } from './system/DiagnosticsResults';
import { ErrorLogsTable } from './system/ErrorLogsTable';

export function SystemHealthPage() {
  const [health, setHealth] = useState<SystemHealthSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
  const [selectedTab, setSelectedTab] = useState(0);

  // Auto-refresh every 30 seconds when enabled
  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const data = await systemApi.getCurrentHealth();
        setHealth(data);
        setError(null);
      } catch (err) {
        setError('Failed to load system health');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchHealth();
    
    if (!autoRefreshEnabled) return;
    
    const interval = setInterval(fetchHealth, 30000);  // 30s polling
    return () => clearInterval(interval);
  }, [autoRefreshEnabled]);

  const handleManualRefresh = async () => {
    setLoading(true);
    try {
      const data = await systemApi.getCurrentHealth();
      setHealth(data);
      setError(null);
    } catch (err) {
      setError('Failed to refresh system health');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  if (loading && !health) {
    return (
      <div
        className="h-full flex items-center justify-center"
        style={{ background: 'var(--color-sentinel-bg-canvas)' }}
      >
        <div className="text-center">
          <RefreshCw
            className="w-8 h-8 animate-spin mx-auto mb-3"
            style={{ color: 'var(--color-sentinel-text-secondary)' }}
          />
          <p style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            Loading system health...
          </p>
        </div>
      </div>
    );
  }

  if (error && !health) {
    return (
      <div
        className="h-full flex items-center justify-center p-4"
        style={{ background: 'var(--color-sentinel-bg-canvas)' }}
      >
        <div
          className="rounded-md p-6 max-w-md text-center"
          style={{
            background: 'rgba(220, 38, 38, 0.1)',
            border: '1px solid rgba(220, 38, 38, 0.3)',
          }}
        >
          <AlertCircle
            className="h-8 w-8 mx-auto mb-3"
            style={{ color: 'var(--color-sentinel-red)' }}
          />
          <h3
            className="text-sm font-medium mb-2"
            style={{ color: 'var(--color-sentinel-red)' }}
          >
            Error
          </h3>
          <p
            className="text-sm mb-4"
            style={{ color: 'var(--color-sentinel-text-secondary)' }}
          >
            {error}
          </p>
          <button
            onClick={handleManualRefresh}
            className="px-4 py-2 rounded text-sm flex items-center gap-2 mx-auto transition-colors hover:opacity-80"
            style={{
              background: 'var(--color-sentinel-bg-secondary)',
              border: '1px solid var(--color-sentinel-border)',
              color: 'var(--color-sentinel-text-primary)',
            }}
          >
            <RefreshCw className="w-4 h-4" />
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      className="h-full overflow-y-auto p-4 md:p-6"
      style={{ background: 'var(--color-sentinel-bg-canvas)' }}
    >
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1
            className="text-xl font-semibold"
            style={{ color: 'var(--color-sentinel-text-primary)' }}
          >
            System Health & Diagnostics
          </h1>
          <p
            className="text-sm"
            style={{ color: 'var(--color-sentinel-text-secondary)' }}
          >
            Unified monitoring of infrastructure health and system diagnostics
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Auto-refresh toggle */}
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefreshEnabled}
              onChange={(e) => setAutoRefreshEnabled(e.target.checked)}
              className="rounded"
            />
            <span
              className="text-xs"
              style={{ color: 'var(--color-sentinel-text-secondary)' }}
            >
              Auto-refresh
            </span>
          </label>

          {/* Manual refresh button */}
          <button
            onClick={handleManualRefresh}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-2 rounded text-sm transition-colors hover:opacity-80"
            style={{
              background: 'var(--color-sentinel-bg-panel)',
              border: '1px solid var(--color-sentinel-border)',
              color: 'var(--color-sentinel-text-secondary)',
            }}
          >
            <RefreshCw
              className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`}
            />
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Health Overview */}
      {health && <HealthOverviewHeader health={health} />}

      {/* Tabs */}
      {/* @ts-ignore - Tremor TabGroup type mismatch */}
      <TabGroup activeTabIndex={selectedTab} onTabChange={(index: number) => setSelectedTab(index)}>
        <TabList>
          <Tab>Realtime Status</Tab>
          <Tab>Historical Insights</Tab>
          <Tab>Diagnostics</Tab>
        </TabList>

        <TabPanels>
          {/* Tab 1: Realtime Status */}
          <TabPanel>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mt-6">
              {health && (
                <>
                  <BMSConnectivityCard health={health} />
                  <APIHealthCard health={health} />
                  <DataFreshnessCard health={health} />
                  <DatabaseStatusCard health={health} />
                  <ServiceHealthCard health={health} />
                </>
              )}
            </div>
          </TabPanel>

          {/* Tab 2: Historical Insights */}
          <TabPanel>
            <div className="space-y-6 mt-6">
              <UptimeMetricsCard />
              <HealthTrendChart />
            </div>
          </TabPanel>

          {/* Tab 3: Diagnostics */}
          <TabPanel>
            <div className="space-y-6 mt-6">
              <DiagnosticsControls />
              <DiagnosticsResults />
              <ErrorLogsTable />
            </div>
          </TabPanel>
        </TabPanels>
      </TabGroup>
    </div>
  );
}

export default SystemHealthPage;
