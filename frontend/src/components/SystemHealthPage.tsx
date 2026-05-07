/**
 * System Health & Diagnostics Dashboard
 *
 * Real-time system health monitoring with four-tab interface:
 * 1. Health - Current health overview and component status
 * 2. Historical Insights - Uptime trends and health trends
 * 3. AI Performance - Optimization run analytics and profile scores
 * 3. Historical - trends and performance snapshots
 */

import { useState, useEffect } from 'react';
import { useServerEvents } from '@/hooks/useServerEvents';
import {
  Card,
  Metric,
  TabGroup,
  TabList,
  Tab,
  TabPanels,
  TabPanel,
  Text,
  ProgressBar,
  LineChart,
} from '@tremor/react';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle,
  Clock,
  Link as LinkIcon,
  Server,
  TrendingUp,
  TrendingDown,
} from 'lucide-react';
import type { IntegrationHealthSummary } from '@/lib/api';
import type { CommissioningSnapshot, QualityGateStatus } from '@/lib/api/system';
import { monitoringApi } from '@/lib/api';
import { authorizedFetch } from '../lib/api/client';

import { PageLoading } from './PageLoading';
import { AdapterHealthCard } from './system/AdapterHealthCard';
import { CriticalPathCard } from './system/CriticalPathCard';
import { CommissioningGatePanel } from './system/CommissioningGatePanel';

interface _HealthComponent {
  name: string;
  status: 'healthy' | 'degraded' | 'critical';
  score: number;
}

interface _HealthSnapshot {
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
  const [dataFreshness, setDataFreshness] = useState<DataFreshnessResponse | null>(null);
  const [commissioning, setCommissioning] = useState<CommissioningSnapshot | null>(null);
  const [qualityGate, setQualityGate] = useState<QualityGateStatus | null>(null);

  // ---- Data Freshness Types ----
  interface FreshnessSource {
    data_source: string;
    age_seconds: number | null;
    target_seconds: number;
    sli_pass: boolean;
    last_updated: string | null;
  }

  interface DataFreshnessResponse {
    site_id: string;
    timestamp: string;
    sources: FreshnessSource[];
    overall_sli_pass: boolean;
    breach_count: number;
  }

  interface DailyUptimeRow {
    check_date: string;
    uptime_percent: number;
    total_checks: number;
    successful_checks: number;
    max_latency_ms: number;
  }

  interface MonthlyUptimeRow {
    month: string;
    uptime_percent: number;
    slo_pass: boolean;
    error_budget_remaining: number;
    downtime_minutes: number;
    total_checks: number;
    successful_checks: number;
    slo_target: number;
  }

  useEffect(() => {
    loadHealthData();
    loadDataFreshness();
    loadUptimeData();
    loadGateData();
    // Refresh health every 30s, freshness every 5m, uptime every 10m, gates every 30s
    const healthInterval = setInterval(loadHealthData, 30000);
    const freshnessInterval = setInterval(loadDataFreshness, 300000);
    const uptimeInterval = setInterval(loadUptimeData, 600000);
    const gateInterval = setInterval(loadGateData, 30000);
    return () => {
      clearInterval(healthInterval);
      clearInterval(freshnessInterval);
      clearInterval(uptimeInterval);
      clearInterval(gateInterval);
    };
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

  const loadDataFreshness = async () => {
    try {
      const siteId = 'S002';
      const res = await authorizedFetch(`/api/system/sites/${siteId}/data-freshness`);
      if (res.ok) {
        const data = await res.json();
        setDataFreshness(data);
      }
    } catch (err) {
      console.error('Data freshness fetch error:', err);
    }
  };

  const [dailyUptime, setDailyUptime] = useState<DailyUptimeRow[]>([]);
  const [monthlyUptime, setMonthlyUptime] = useState<MonthlyUptimeRow | null>(null);

  const loadUptimeData = async () => {
    try {
      const [dailyRes, monthlyRes] = await Promise.all([
        authorizedFetch('/api/system/uptime/daily?days=30'),
        authorizedFetch('/api/system/uptime/monthly/current'),
      ]);

      if (dailyRes.ok) {
        const data = await dailyRes.json();
        setDailyUptime(data.data || []);
      }

      if (monthlyRes.ok) {
        const data = await monthlyRes.json();
        setMonthlyUptime(data.data || null);
      }
    } catch (err) {
      console.error('Uptime data fetch error:', err);
    }
  };

  const loadGateData = async () => {
    try {
      const siteId = 'site-002';
      const [scorecardRes, qgRes] = await Promise.all([
        authorizedFetch(`/api/integration/buildings/${siteId}/commissioning-scorecard`),
        authorizedFetch(`/api/optimization/quality-gate/${siteId}`),
      ]);
      if (scorecardRes.ok) {
        const data = await scorecardRes.json();
        setCommissioning(data);
      }
      if (qgRes.ok) {
        const data = await qgRes.json();
        setQualityGate(data);
      }
    } catch (err) {
      console.error('Gate data fetch error:', err);
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
  const healthTrendData = (history?.snapshots || [])
    .map((snapshot: any) => {
      const score = Number(snapshot?.overall_score);
      if (!Number.isFinite(score)) return null;

      const parsedTimestamp = snapshot?.timestamp ? new Date(snapshot.timestamp) : null;
      const date =
        parsedTimestamp && !Number.isNaN(parsedTimestamp.getTime())
          ? parsedTimestamp.toLocaleTimeString()
          : String(snapshot?.timestamp || "Unknown");

      return { date, score };
    })
    .filter((point: { date: string; score: number } | null): point is { date: string; score: number } => point !== null);

  return (
    <div className="h-full overflow-y-auto p-4 md:p-6" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
      {/* Page Header — matches Lighting tab pattern */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(99, 102, 241, 0.15)" }}>
              <Server className="h-6 w-6" style={{ color: "var(--color-sentinel-purple)" }} />
            </div>
            <div>
              <h1 className="text-2xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                System Health
              </h1>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Real-time monitoring &amp; diagnostics
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Tab Interface */}
      <TabGroup defaultIndex={selectedTab} onIndexChange={setSelectedTab}>
        <TabList className="mb-4 overflow-x-auto rounded-lg border" style={{ borderColor: "var(--color-sentinel-border)" }}>
          <Tab>Health</Tab>
          <Tab>Historical</Tab>
        </TabList>

        <TabPanels>
          {/* TAB 1: REALTIME STATUS */}
          <TabPanel className="space-y-6">
            {currentHealth && (
              <>
                {/* Overall Health Card */}
                <Card className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
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
                      className="inline-flex items-center gap-2 rounded-lg px-3 py-2 h-fit"
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
                <Card className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
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
                    <div className="rounded-lg p-2.5" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--color-sentinel-border)" }}>
                      <Text style={{ color: "var(--color-sentinel-text-secondary)" }} className="uppercase text-[10px] tracking-wide">Sources</Text>
                      <Metric style={{ color: "var(--color-sentinel-text-primary)" }}>{integrationHealth?.sources_count || 0}</Metric>
                    </div>
                    <div className="rounded-lg p-2.5" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--color-sentinel-border)" }}>
                      <Text style={{ color: "var(--color-sentinel-text-secondary)" }} className="uppercase text-[10px] tracking-wide">Records</Text>
                      <Metric style={{ color: "var(--color-sentinel-text-primary)" }}>{integrationHealth?.total_records_ingested || 0}</Metric>
                    </div>
                    <div className="rounded-lg p-2.5" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--color-sentinel-border)" }}>
                      <Text style={{ color: "var(--color-sentinel-text-secondary)" }} className="uppercase text-[10px] tracking-wide">Mapped Points</Text>
                      <Metric style={{ color: "var(--color-sentinel-text-primary)" }}>{integrationHealth?.total_points_mapped || 0}</Metric>
                    </div>
                    <div className="rounded-lg p-2.5" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--color-sentinel-border)" }}>
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

                {/* Commissioning Gates + Quality Gate */}
                <CommissioningGatePanel
                  commissioning={commissioning}
                  qualityGate={qualityGate}
                />

                {/* Adapter Health — SLI Tier 1 */}
                <AdapterHealthCard siteId="site-002" />

                {/* Component Status Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {Object.entries(currentHealth.components || {}).map(
                    ([key, component]: [string, any]) => {
                      const labels: Record<string, string> = {
                        supabase: "Supabase",
                        redis_cache: "Redis Cache",
                        event_bus: "Event Bus",
                        n8n: "n8n Workflows",
                        servicenow: "ServiceNow",
                        notifications: "Notifications",
                        device_manager: "Device Manager",
                      };
                      return (
                        <Card key={key} className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
                          <div className="flex items-start justify-between">
                            <div className="flex-1">
                              <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>
                                {labels[key] || key}
                              </Text>
                              <Metric style={{ color: "var(--color-sentinel-text-primary)" }}>{component.score}</Metric>
                            </div>
                            {getStatusIcon(component.status)}
                          </div>
                          <ProgressBar
                            value={component.score}
                            color={getStatusColor(component.status)}
                            className="mt-2"
                          />
                          {component.message && (
                            <Text className="mt-2 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                              {component.message}
                            </Text>
                          )}
                        </Card>
                      );
                    }
                  )}
                </div>
              </>
            )}
            </TabPanel>
            {/* TAB 2: DATA FRESHNESS */}
            <TabPanel className="space-y-6">
            <Card className="rounded-lg p-5" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
              <div className="pb-3">
                <div className="flex items-center justify-between">
                  <Text className="text-base font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Data Freshness</Text>
                  <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    {dataFreshness?.timestamp && new Date(dataFreshness.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              </div>
              <div>
                {dataFreshness && dataFreshness.breach_count > 0 && (
                  <div className="mb-4 p-3 rounded-lg flex items-start gap-2" style={{ background: "rgba(234, 179, 8, 0.12)", border: "1px solid rgba(234, 179, 8, 0.35)" }}>
                    <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" style={{ color: "var(--color-sentinel-yellow)" }} />
                    <div>
                      <p className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>Stale Data Detected</p>
                      <p className="text-xs mt-0.5" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                        {dataFreshness.breach_count} source(s) exceed SLI target
                      </p>
                    </div>
                  </div>
                )}
                {(!dataFreshness || dataFreshness.sources.length === 0) && (
                  <Text className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>No freshness data available</Text>
                )}
                <div className="space-y-3">
                  {dataFreshness?.sources.map((source: FreshnessSource) => {
                    const agePct = source.age_seconds != null
                      ? Math.min(100, (source.age_seconds / source.target_seconds) * 100)
                      : 0;
                    return (
                      <div
                        key={source.data_source}
                        className="p-3 rounded"
                        style={{
                          background: source.sli_pass ? "rgba(34, 197, 94, 0.08)" : "rgba(234, 179, 8, 0.08)",
                          border: `1px solid ${source.sli_pass ? "rgba(34, 197, 94, 0.3)" : "rgba(234, 179, 8, 0.3)"}`,
                        }}
                      >
                        <div className="flex items-center justify-between mb-1.5">
                          <div className="flex items-center gap-1.5">
                            {source.sli_pass
                              ? <CheckCircle className="w-3.5 h-3.5" style={{ color: "#22c55e" }} />
                              : <AlertTriangle className="w-3.5 h-3.5" style={{ color: "#eab308" }} />}
                            <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                              {source.data_source.replace(/_/g, " ")}
                            </span>
                          </div>
                          <span
                            className="text-xs font-mono font-bold"
                            style={{ color: source.sli_pass ? "#22c55e" : "#eab308" }}
                          >
                            {source.age_seconds != null ? (
                              source.age_seconds < 60
                                ? `${source.age_seconds}s`
                                : source.age_seconds < 3600
                                  ? `${Math.floor(source.age_seconds / 60)}m`
                                  : `${Math.floor(source.age_seconds / 3600)}h`
                            ) : "N/A"} / {source.target_seconds < 60
                              ? `${source.target_seconds}s`
                              : source.target_seconds < 3600
                                ? `${Math.floor(source.target_seconds / 60)}m`
                                : `${Math.floor(source.target_seconds / 3600)}h`}
                          </span>
                        </div>
                        <div className="w-full rounded-full h-1.5 overflow-hidden" style={{ background: "rgba(148, 163, 184, 0.2)" }}>
                          <div
                            className="h-1.5 rounded-full transition-all duration-500"
                            style={{ width: `${agePct}%`, background: source.sli_pass ? "#22c55e" : "#eab308" }}
                          />
                        </div>
                        {source.last_updated && (
                          <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                            Updated {new Date(source.last_updated).toLocaleTimeString()}
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </Card>
            </TabPanel>

          {/* TAB 3: HISTORICAL INSIGHTS */}
          <TabPanel className="space-y-6">
            {history && (
              <>
                {/* Uptime Metrics */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  <Card className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
                    <Text className="uppercase text-[11px] tracking-wide" style={{ color: "var(--color-sentinel-text-secondary)" }}>Average Health Score</Text>
                    <Metric style={{ color: "var(--color-sentinel-text-primary)", fontVariantNumeric: "tabular-nums" }}>{history.metrics?.avg_score || 0}</Metric>
                  </Card>
                  <Card className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
                    <Text className="uppercase text-[11px] tracking-wide" style={{ color: "var(--color-sentinel-text-secondary)" }}>Uptime ({history.range})</Text>
                    <Metric style={{ color: "var(--color-sentinel-text-primary)", fontVariantNumeric: "tabular-nums" }}>
                      {history.metrics?.uptime_percentage || 0}%
                    </Metric>
                  </Card>
                  <Card className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
                    <Text className="uppercase text-[11px] tracking-wide" style={{ color: "var(--color-sentinel-text-secondary)" }}>Min Score</Text>
                    <Metric style={{ color: "var(--color-sentinel-text-primary)", fontVariantNumeric: "tabular-nums" }}>{history.metrics?.min_score || 0}</Metric>
                  </Card>
                  <Card className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
                    <Text className="uppercase text-[11px] tracking-wide" style={{ color: "var(--color-sentinel-text-secondary)" }}>Max Score</Text>
                    <Metric style={{ color: "var(--color-sentinel-text-primary)", fontVariantNumeric: "tabular-nums" }}>{history.metrics?.max_score || 0}</Metric>
                  </Card>
                </div>

                {/* Trend Analysis */}
                <Card className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
                  <Text className="uppercase text-[11px] tracking-wide" style={{ color: "var(--color-sentinel-text-secondary)" }}>Trend</Text>
                  <div className="flex items-center gap-2 mt-2">
                    {history.metrics?.trend === 'improving' && (
                      <>
                        <TrendingUp className="w-5 h-5 text-green-500" />
                        <span className="text-xs font-semibold px-2 py-1 rounded" style={{ background: "rgba(16, 185, 129, 0.15)", border: "1px solid rgba(16, 185, 129, 0.35)", color: "var(--color-sentinel-green)" }}>Improving</span>
                      </>
                    )}
                    {history.metrics?.trend === 'degrading' && (
                      <>
                        <TrendingDown className="w-5 h-5 text-red-500" />
                        <span className="text-xs font-semibold px-2 py-1 rounded" style={{ background: "rgba(220, 38, 38, 0.15)", border: "1px solid rgba(220, 38, 38, 0.35)", color: "var(--color-sentinel-red)" }}>Degrading</span>
                      </>
                    )}
                    {history.metrics?.trend === 'stable' && (
                      <>
                        <Clock className="w-5 h-5 text-gray-500" />
                        <span className="text-xs font-semibold px-2 py-1 rounded" style={{ background: "rgba(148, 163, 184, 0.15)", border: "1px solid rgba(148, 163, 184, 0.35)", color: "var(--color-sentinel-text-secondary)" }}>Stable</span>
                      </>
                    )}
                  </div>
                </Card>

                {/* Health Score Chart */}
                {healthTrendData.length > 0 && (
                  <Card className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
                    <Text className="uppercase text-[11px] tracking-wide" style={{ color: "var(--color-sentinel-text-secondary)" }}>Health Score Trend</Text>
                    <LineChart
                      className="mt-6"
                      data={healthTrendData}
                      index="date"
                      yAxisWidth={40}
                      categories={['score']}
                      colors={['blue']}
                      showLegend={false}
                    />
                  </Card>
                )}
                {healthTrendData.length === 0 && (
                  <Card className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
                    <Text className="uppercase text-[11px] tracking-wide" style={{ color: "var(--color-sentinel-text-secondary)" }}>Health Score Trend</Text>
                    <Text className="mt-3" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      No valid health score points are available for this range yet.
                    </Text>
                  </Card>
                )}

                {/* Availability SLI Card */}
                {monthlyUptime && (
                  <Card className="rounded-lg p-5" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
                    <div className="pb-3">
                      <div className="flex items-center justify-between">
                        <Text className="text-base font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Availability SLI</Text>
                        <span className="text-xs font-medium px-2 py-1 rounded" style={{
                          background: monthlyUptime.slo_pass ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.12)",
                          border: `1px solid ${monthlyUptime.slo_pass ? "rgba(34,197,94,0.35)" : "rgba(239,68,68,0.35)"}`,
                          color: monthlyUptime.slo_pass ? "var(--color-sentinel-green)" : "var(--color-sentinel-red)",
                        }}>
                          {monthlyUptime.slo_pass ? "✅ SLO PASS" : "❌ SLO FAIL"}
                        </span>
                      </div>
                      <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                        Target: 99.5% uptime · Checks every 60s
                      </Text>
                    </div>

                    <div className="mb-4 p-4 rounded-lg" style={{
                      background: monthlyUptime.slo_pass ? "rgba(34,197,94,0.08)" : "rgba(239,68,68,0.08)",
                      border: `1px solid ${monthlyUptime.slo_pass ? "rgba(34,197,94,0.3)" : "rgba(239,68,68,0.3)"}`,
                    }}>
                      <div className="flex items-baseline justify-between">
                        <div>
                          <Text className="text-xs uppercase tracking-wide" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                            This Month ({monthlyUptime.month})
                          </Text>
                          <Metric style={{ color: "var(--color-sentinel-text-primary)", fontVariantNumeric: "tabular-nums" }}>
                            {monthlyUptime.uptime_percent}%
                          </Metric>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-bold" style={{ color: monthlyUptime.slo_pass ? "var(--color-sentinel-green)" : "var(--color-sentinel-red)" }}>
                            {monthlyUptime.uptime_percent >= 99.5 ? "✓" : "✗"} {monthlyUptime.uptime_percent.toFixed(3)}%
                          </p>
                          <p className="text-xs mt-0.5" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                            Budget: {monthlyUptime.error_budget_remaining.toFixed(3)}% remaining
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* Last 30 days mini-calendar */}
                    {dailyUptime.length > 0 && (
                      <div className="mb-3">
                        <Text className="text-xs font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>Last 30 Days</Text>
                        <div className="grid grid-cols-10 gap-1 mt-2">
                          {dailyUptime.slice(-30).map((day: DailyUptimeRow) => {
                            const pct = day.uptime_percent;
                            const color = pct >= 99.5 ? "#22c55e" : pct >= 95 ? "#eab308" : "#ef4444";
                            return (
                              <div
                                key={day.check_date}
                                className="w-full aspect-square rounded-sm flex items-center justify-center cursor-default transition-opacity hover:opacity-80"
                                style={{ background: color }}
                                title={`${day.check_date}: ${pct.toFixed(1)}%`}
                              />
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {/* Metrics row */}
                    <div className="grid grid-cols-2 gap-3">
                      <div className="rounded p-2.5" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--color-sentinel-border)" }}>
                        <Text className="text-xs uppercase tracking-wide" style={{ color: "var(--color-sentinel-text-secondary)" }}>Downtime</Text>
                        <p className="text-base font-bold font-mono" style={{ color: "var(--color-sentinel-text-primary)" }}>
                          {monthlyUptime.downtime_minutes.toFixed(1)} min
                        </p>
                      </div>
                      <div className="rounded p-2.5" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--color-sentinel-border)" }}>
                        <Text className="text-xs uppercase tracking-wide" style={{ color: "var(--color-sentinel-text-secondary)" }}>Checks Run</Text>
                        <p className="text-base font-bold font-mono" style={{ color: "var(--color-sentinel-text-primary)" }}>
                          {monthlyUptime.total_checks?.toLocaleString() ?? "—"}
                        </p>
                      </div>
                    </div>
                  </Card>
                )}

                {/* Critical Path Latency Card — SLI Tier 3 */}
                <CriticalPathCard siteId="site-002" />
              </>
            )}
          </TabPanel>

        </TabPanels>
      </TabGroup>
    </div>
  );
}
