/**
 * System Health & Diagnostics Dashboard
 *
 * Real-time system health monitoring with three-tab interface:
 * 1. Realtime Status - Current health overview and component status
 * 2. Historical Insights - Uptime trends and health trends
 * 3. Diagnostics - SIMBIOT diagnostic tools and error logs
 */

import { useState, useEffect } from 'react';
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
  TrendingUp,
  TrendingDown,
} from 'lucide-react';
import { authorizedFetch } from '../lib/api/client';

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
  const [selectedTab, setSelectedTab] = useState(0);
  const [currentHealth, setCurrentHealth] = useState<any>(null);
  const [history, setHistory] = useState<any>(null);
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

      // Fetch current health with authentication
      const healthRes = await authorizedFetch('/api/system/health');
      if (!healthRes.ok) throw new Error('Failed to fetch health');
      const health = await healthRes.json();
      setCurrentHealth(health);

      // Fetch history with authentication
      const historyRes = await authorizedFetch('/api/system/health/history?range=24h');
      if (!historyRes.ok) throw new Error('Failed to fetch history');
      const hist = await historyRes.json();
      setHistory(hist);
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

  if (loading && !currentHealth) {
    return (
      <div className="p-6">
        <Text>Loading system health data...</Text>
      </div>
    );
  }

  if (error && !currentHealth) {
    return (
      <div className="p-6">
        <Card>
          <div className="flex items-center gap-2">
            <AlertCircle className="w-5 h-5 text-red-500" />
            <Text className="text-red-500">Error: {error}</Text>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold">System Health Dashboard</h1>
        <Text className="text-gray-500">Real-time monitoring and diagnostics</Text>
      </div>

      {/* Tab Interface */}
      <TabGroup defaultIndex={selectedTab} onIndexChange={setSelectedTab}>
        <TabList>
          <Tab>Realtime Status</Tab>
          <Tab>Historical Insights</Tab>
          <Tab>Diagnostics</Tab>
        </TabList>

        <TabPanels>
          {/* TAB 1: REALTIME STATUS */}
          <TabPanel className="space-y-6">
            {currentHealth && (
              <>
                {/* Overall Health Card */}
                <Card>
                  <div className="flex items-center justify-between">
                    <div>
                      <Text>Overall Health Status</Text>
                      <Metric>{currentHealth.overall_score}</Metric>
                    </div>
                    <div className="text-right">
                      <Badge
                        color={getStatusColor(currentHealth.overall_status)}
                      >
                        {currentHealth.overall_status.toUpperCase()}
                      </Badge>
                    </div>
                  </div>
                  <ProgressBar
                    value={currentHealth.overall_score}
                    color={getStatusColor(currentHealth.overall_status)}
                    className="mt-4"
                  />
                </Card>

                {/* Component Status Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {Object.entries(currentHealth.components || {}).map(
                    ([key, component]: [string, any]) => (
                      <Card key={key}>
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <Text className="capitalize">{key}</Text>
                            <Metric>{component.score}</Metric>
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
                  <Card>
                    <Text>Average Health Score</Text>
                    <Metric>{history.metrics?.avg_score || 0}</Metric>
                  </Card>
                  <Card>
                    <Text>Uptime ({history.range})</Text>
                    <Metric>
                      {history.metrics?.uptime_percentage || 0}%
                    </Metric>
                  </Card>
                  <Card>
                    <Text>Min Score</Text>
                    <Metric>{history.metrics?.min_score || 0}</Metric>
                  </Card>
                  <Card>
                    <Text>Max Score</Text>
                    <Metric>{history.metrics?.max_score || 0}</Metric>
                  </Card>
                </div>

                {/* Trend Analysis */}
                <Card>
                  <Text>Trend</Text>
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
                  <Card>
                    <Text>Health Score Trend</Text>
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

          {/* TAB 3: DIAGNOSTICS */}
          <TabPanel className="space-y-6">
            <Card>
              <div className="text-center py-8">
                <Text className="text-gray-500">
                  Diagnostics tools coming soon
                </Text>
                <p className="text-sm text-gray-400 mt-2">
                  Run SIMBIOT diagnostics to analyze system components
                </p>
              </div>
            </Card>
          </TabPanel>
        </TabPanels>
      </TabGroup>
    </div>
  );
}
