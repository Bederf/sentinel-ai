/**
 * System Health & Diagnostics Dashboard
 *
 * Real-time system health monitoring with four-tab interface:
 * 1. Health - Current health overview and component status
 * 2. Historical Insights - Uptime trends and health trends
 * 3. AI Performance - Optimization run analytics and profile scores
 * 4. Model Health - ML model freshness, accuracy, and A/B tests
 */

import { useState, useEffect } from 'react';
import { useServerEvents } from '@/hooks/useServerEvents';
import {
  TabGroup,
  TabList,
  Tab,
  TabPanels,
  TabPanel,
  Card,
  Text,
  Metric,
  ProgressBar,
  LineChart,
  BarChart,
  Badge,
} from '@tremor/react';
import {
  AlertCircle,
  CheckCircle,
  Clock,
  Link as LinkIcon,
  Server,
  TrendingUp,
  TrendingDown,
} from 'lucide-react';
import type { IntegrationHealthSummary } from '@/lib/api';
import { monitoringApi } from '@/lib/api';
import { authorizedFetch } from '../lib/api/client';
import { PageLoading } from './PageLoading';
import { AIPerformanceTab } from './system/AIPerformanceTab';
import { ModelHealthTab } from './system/ModelHealthTab';

interface HealthComponent {
  name: string;
  status: 'healthy' | 'degraded' | 'critical';
  score: number;
}

interface HealthSnapshot {
  timestamp: string;
  overall_score: number;
  overall_status: string;
}

export default function SystemHealthPage() {
  // Real-time event updates from backend SSE
  useServerEvents();

  const [selectedTab, setSelectedTab] = useState(0);
  const [currentHealth, setCurrentHealth] = useState<any>(null);
  const [history, setHistory] = useState<any>(null);
  const [integrationHealth, setIntegrationHealth] = useState<IntegrationHealthSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadHealthData();
    // Refresh every 30 seconds
    const interval = setInterval(loadHealthData, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadHealthData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [healthRes, historyRes, integration] = await Promise.all([
        authorizedFetch('/api/system/health'),
        authorizedFetch('/api/system/health/history?range=24h'),
        monitoringApi.getIntegrationHealth(),
      ]);

      if (!healthRes.ok) throw new Error('Failed to fetch health');
      const health = await healthRes.json();
      setCurrentHealth(health);

      if (!historyRes.ok) throw new Error('Failed to fetch history');
      const hist = await historyRes.json();
      setHistory(hist);
      setIntegrationHealth(integration);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      console.error('Health data load error:', err);
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'green';
      case 'degraded':
        return 'yellow';
      case 'critical':
        return 'red';
      default:
        return 'gray';
    }
  };

  const getStatusTone = (status: string) => {
    switch (status) {
      case 'healthy':
        return {
          accent: 'var(--color-sentinel-green)',
          bg: 'rgba(16, 185, 129, 0.15)',
          border: 'rgba(16, 185, 129, 0.35)',
        };
      case 'degraded':
        return {
          accent: 'var(--color-sentinel-amber)',
          bg: 'rgba(245, 158, 11, 0.15)',
          border: 'rgba(245, 158, 11, 0.35)',
        };
      case 'critical':
        return {
          accent: 'var(--color-sentinel-red)',
          bg: 'rgba(220, 38, 38, 0.15)',
          border: 'rgba(220, 38, 38, 0.35)',
        };
      default:
        return {
          accent: 'var(--color-sentinel-text-secondary)',
          bg: 'rgba(148, 163, 184, 0.12)',
          border: 'rgba(148, 163, 184, 0.25)',
        };
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
        return <CheckCircle className="w-5 h-5 text-green-500" />;
      case 'degraded':
        return <AlertCircle className="w-5 h-5 text-yellow-500" />;
      case 'critical':
        return <AlertCircle className="w-5 h-5 text-red-500" />;
      default:
        return <Clock className="w-5 h-5 text-gray-500" />;
    }
  };

  const formatRelativeTime = (dateStr: string | null) => {
    if (!dateStr) return 'No sync recorded';
    const date = new Date(dateStr);
    if (isNaN(date.getTime())) return 'Unknown';
    const diffMs = Date.now() - date.getTime();
    const diffMinutes = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMinutes / 60);
    const diffDays = Math.floor(diffHours / 24);
    if (diffMinutes < 60) return `${diffMinutes}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
  };

  if (loading && !currentHealth) {
    return <PageLoading message="Loading system health data..." />;
  }

  if (error && !currentHealth) {
    return (
      <div className="p-6">
        <Card className="glass-panel" style={{ border: "1px solid rgba(220, 38, 38, 0.35)" }}>
          <div className="flex items-center gap-2">
            <AlertCircle className="w-5 h-5 text-red-500" />
            <Text className="text-red-500">Error: {error}</Text>
          </div>
        </Card>
      </div>
    );
  }

  const overallStatus = currentHealth?.overall_status || 'healthy';
  const overallTone = getStatusTone(overallStatus);

  return (
    <div className="p-6 space-y-6" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
      {/* Page Header */}
      <div
        className="glass-panel rounded-lg p-5"
        style={{ border: "1px solid var(--glass-border)" }}
      >
        <h1
          className="text-2xl font-semibold tracking-tight"
          style={{ color: "var(--color-sentinel-text-primary)" }}
        >
          System Health Dashboard
        </h1>
        <p className="text-sm mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Real-time monitoring and diagnostics
        </p>
      </div>

      {/* Tab Interface */}
      <TabGroup defaultIndex={selectedTab} onIndexChange={setSelectedTab}>
        <TabList className="glass-subtle rounded-md p-1" style={{ border: "1px solid var(--glass-border)" }}>
          <Tab>Health</Tab>
          <Tab>Historical Insights</Tab>
          <Tab>AI Performance</Tab>
          <Tab>Model Health</Tab>
        </TabList>

        <TabPanels>
          {/* TAB 1: REALTIME STATUS */}
          <TabPanel className="space-y-6">
            {currentHealth && (
              <>
                {/* Overall Health Card */}
                <Card className="glass-panel" style={{ border: "1px solid var(--glass-border)" }}>
                  <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
                    <div className="space-y-2">
                      <p
                        className="text-xs uppercase tracking-wider font-medium"
                        style={{ color: "var(--color-sentinel-text-secondary)" }}
                      >
                        Overall Health Status
                      </p>
                      <div className="flex items-end gap-3">
                        <span
                          className="text-6xl font-semibold leading-none"
                          style={{ color: "var(--color-sentinel-text-primary)" }}
                        >
                          {currentHealth.overall_score}
                        </span>
                        <span
                          className="text-sm pb-1"
                          style={{ color: "var(--color-sentinel-text-secondary)" }}
                        >
                          /100
                        </span>
                      </div>
                    </div>
                    <div
                      className="inline-flex items-center gap-2 rounded-md px-3 py-2 h-fit"
                      style={{
                        background: overallTone.bg,
                        border: `1px solid ${overallTone.border}`,
                      }}
                    >
                      <span
                        className="inline-block h-2.5 w-2.5 rounded-full"
                        style={{ background: overallTone.accent }}
                      />
                      <span
                        className="text-xs font-semibold tracking-wide"
                        style={{ color: overallTone.accent }}
                      >
                        {overallStatus.toUpperCase()}
                      </span>
                    </div>
                  </div>
                  <ProgressBar
                    value={currentHealth.overall_score}
                    color={getStatusColor(overallStatus)}
                    className="mt-4"
                  />
                </Card>

                {/* Integration Status */}
                <Card className="glass-panel" style={{ border: "1px solid var(--glass-border)" }}>
                  <div className="flex items-start justify-between">
                    <div>
                      <p
                        className="text-xs uppercase tracking-wider font-medium"
                        style={{ color: "var(--color-sentinel-text-secondary)" }}
                      >
                        Integration Status
                      </p>
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <span
                          className="inline-flex items-center rounded px-2 py-1 text-xs font-medium"
                          style={{
                            background: integrationHealth?.active_sources ? "rgba(16, 185, 129, 0.15)" : "rgba(245, 158, 11, 0.15)",
                            border: integrationHealth?.active_sources ? "1px solid rgba(16, 185, 129, 0.35)" : "1px solid rgba(245, 158, 11, 0.35)",
                            color: integrationHealth?.active_sources ? "var(--color-sentinel-green)" : "var(--color-sentinel-amber)",
                          }}
                        >
                          {integrationHealth?.active_sources || 0} active source(s)
                        </span>
                        <span style={{ color: "var(--color-sentinel-text-disabled)", fontSize: "0.75rem" }}>•</span>
                        <span
                          className="inline-flex items-center rounded px-2 py-1 text-xs"
                          style={{
                            background: "var(--color-sentinel-bg-secondary)",
                            border: "1px solid var(--glass-border)",
                            color: "var(--color-sentinel-text-secondary)",
                          }}
                        >
                          Sync age: {formatRelativeTime(integrationHealth?.last_sync || null)}
                        </span>
                      </div>
                    </div>
                    <Server className="w-5 h-5" style={{ color: "var(--color-sentinel-blue)" }} />
                  </div>
                  <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className="rounded-md p-2.5" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}>
                      <Text style={{ color: "var(--color-sentinel-text-secondary)" }} className="uppercase text-[10px] tracking-wide">Sources</Text>
                      <Metric style={{ color: "var(--color-sentinel-text-primary)" }}>{integrationHealth?.sources_count || 0}</Metric>
                    </div>
                    <div className="rounded-md p-2.5" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}>
                      <Text style={{ color: "var(--color-sentinel-text-secondary)" }} className="uppercase text-[10px] tracking-wide">Records</Text>
                      <Metric style={{ color: "var(--color-sentinel-text-primary)" }}>{integrationHealth?.total_records_ingested || 0}</Metric>
                    </div>
                    <div className="rounded-md p-2.5" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}>
                      <Text style={{ color: "var(--color-sentinel-text-secondary)" }} className="uppercase text-[10px] tracking-wide">Mapped Points</Text>
                      <Metric style={{ color: "var(--color-sentinel-text-primary)" }}>{integrationHealth?.total_points_mapped || 0}</Metric>
                    </div>
                    <div className="rounded-md p-2.5" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}>
                      <Text style={{ color: "var(--color-sentinel-text-secondary)" }} className="uppercase text-[10px] tracking-wide">Unmatched</Text>
                      <Metric style={{ color: "var(--color-sentinel-text-primary)" }}>{integrationHealth?.unmatched_points || 0}</Metric>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <LinkIcon className="w-4 h-4 text-amber-500" />
                      <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>Active alerts: {integrationHealth?.alerts?.length || 0}</Text>
                    </div>
                    <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>Recent errors: {integrationHealth?.recent_errors_count || 0}</Text>
                  </div>
                </Card>

                {/* Component Status Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {Object.entries(currentHealth.components || {}).map(
                    ([key, component]: [string, any]) => (
                      <Card key={key} className="glass-panel" style={{ border: "1px solid var(--glass-border)" }}>
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <Text className="capitalize" style={{ color: "var(--color-sentinel-text-secondary)" }}>{key}</Text>
                            <Metric style={{ color: "var(--color-sentinel-text-primary)" }}>{component.score}</Metric>
                          </div>
                          {getStatusIcon(component.status)}
                        </div>
                        <ProgressBar
                          value={component.score}
                          color={getStatusColor(component.status)}
                          className="mt-2"
                        />
                      </Card>
                    )
                  )}
                </div>
              </>
            )}
          </TabPanel>

          {/* TAB 2: HISTORICAL INSIGHTS */}
          <TabPanel className="space-y-6">
            {history && (
              <>
                {/* Uptime Metrics */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  <Card className="glass-panel" style={{ border: "1px solid var(--glass-border)" }}>
                    <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>Average Health Score</Text>
                    <Metric style={{ color: "var(--color-sentinel-text-primary)" }}>{history.metrics?.avg_score || 0}</Metric>
                  </Card>
                  <Card className="glass-panel" style={{ border: "1px solid var(--glass-border)" }}>
                    <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>Uptime ({history.range})</Text>
                    <Metric style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {history.metrics?.uptime_percentage || 0}%
                    </Metric>
                  </Card>
                  <Card className="glass-panel" style={{ border: "1px solid var(--glass-border)" }}>
                    <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>Min Score</Text>
                    <Metric style={{ color: "var(--color-sentinel-text-primary)" }}>{history.metrics?.min_score || 0}</Metric>
                  </Card>
                  <Card className="glass-panel" style={{ border: "1px solid var(--glass-border)" }}>
                    <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>Max Score</Text>
                    <Metric style={{ color: "var(--color-sentinel-text-primary)" }}>{history.metrics?.max_score || 0}</Metric>
                  </Card>
                </div>

                {/* Trend Analysis */}
                <Card className="glass-panel" style={{ border: "1px solid var(--glass-border)" }}>
                  <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>Trend</Text>
                  <div className="flex items-center gap-2 mt-2">
                    {history.metrics?.trend === 'improving' && (
                      <>
                        <TrendingUp className="w-5 h-5 text-green-500" />
                        <Badge color="green">Improving</Badge>
                      </>
                    )}
                    {history.metrics?.trend === 'degrading' && (
                      <>
                        <TrendingDown className="w-5 h-5 text-red-500" />
                        <Badge color="red">Degrading</Badge>
                      </>
                    )}
                    {history.metrics?.trend === 'stable' && (
                      <>
                        <Clock className="w-5 h-5 text-gray-500" />
                        <Badge color="gray">Stable</Badge>
                      </>
                    )}
                  </div>
                </Card>

                {/* Health Score Chart */}
                {history.snapshots && history.snapshots.length > 0 && (
                  <Card className="glass-panel" style={{ border: "1px solid var(--glass-border)" }}>
                    <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>Health Score Trend</Text>
                    <LineChart
                      className="mt-6"
                      data={history.snapshots.map((s: any) => ({
                        date: new Date(s.timestamp).toLocaleTimeString(),
                        score: s.overall_score,
                      }))}
                      index="date"
                      yAxisWidth={40}
                      categories={['score']}
                    />
                  </Card>
                )}
              </>
            )}
          </TabPanel>

          {/* TAB 3: AI PERFORMANCE */}
          <TabPanel className="space-y-6">
            <AIPerformanceTab />
          </TabPanel>

          {/* TAB 4: MODEL HEALTH */}
          <TabPanel className="space-y-6">
            <ModelHealthTab />
          </TabPanel>
        </TabPanels>
      </TabGroup>
    </div>
  );
}
