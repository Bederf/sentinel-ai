/**
 * Dashboard Component - Main dashboard view with grid layout
 *
 * Features:
 * - Grid layout for cards and charts
 * - Header with title
 * - Placeholder sections for future content:
 *   - KPIs (top row)
 *   - Site Overview (left column)
 *   - Alerts Feed (right column)
 *   - Charts (bottom area)
 */

import { useState, useEffect } from "react";
import {
  Card,
  Title,
  Text,
  Grid,
  Col,
  Metric,
  Badge,
  Flex,
} from "@tremor/react";
import {
  Building2,
  AlertTriangle,
  Activity,
  Cpu,
  TrendingUp,
  Bell,
} from "lucide-react";
import api, { DashboardStats, Alert, Site, Anomaly } from "../lib/api";

// KPI Card component for top row
interface KPICardProps {
  title: string;
  value: string | number;
  icon: React.ReactNode;
  trend?: string;
  trendColor?: "green" | "red" | "gray";
}

function KPICard({ title, value, icon, trend, trendColor = "gray" }: KPICardProps) {
  return (
    <Card className="p-4">
      <Flex justifyContent="start" className="gap-4">
        <div className="p-3 bg-bidvest-blue-50 rounded-lg">{icon}</div>
        <div>
          <Text className="text-gray-500">{title}</Text>
          <Metric className="text-2xl font-bold text-gray-900">{value}</Metric>
          {trend && (
            <Badge color={trendColor} size="sm" className="mt-1">
              {trend}
            </Badge>
          )}
        </div>
      </Flex>
    </Card>
  );
}

export function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [sites, setSites] = useState<Site[]>([]);
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadDashboardData = async () => {
      try {
        setLoading(true);
        // Load all data in parallel
        const [statsData, alertsData, sitesData, anomaliesData] = await Promise.all([
          api.getStats(),
          api.getAlerts(),
          api.getSites(),
          api.getAnomalies(),
        ]);
        setStats(statsData);
        setAlerts(alertsData);
        setSites(sitesData);
        setAnomalies(anomaliesData);
        setError(null);
      } catch (err) {
        console.error("Failed to load dashboard data:", err);
        setError("Failed to load dashboard data");
      } finally {
        setLoading(false);
      }
    };

    loadDashboardData();
  }, []);

  // Calculate critical and warning counts from alerts
  const criticalAlerts = alerts.filter((a) => a.severity === "critical").length;
  const highAlerts = alerts.filter((a) => a.severity === "high").length;

  // Get site status counts
  const normalSites = sites.filter((s) => s.status === "normal").length;
  const warningSites = sites.filter((s) => s.status === "warning").length;
  const criticalSites = sites.filter((s) => s.status === "critical").length;

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin h-8 w-8 border-4 border-bidvest-blue-600 border-t-transparent rounded-full mx-auto mb-4" />
          <Text>Loading dashboard data...</Text>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center">
        <Card className="p-8 text-center">
          <AlertTriangle className="h-12 w-12 text-red-500 mx-auto mb-4" />
          <Title>Error Loading Dashboard</Title>
          <Text className="text-gray-500">{error}</Text>
        </Card>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      {/* Header */}
      <div className="mb-6">
        <Title className="text-2xl font-bold text-gray-900">Dashboard</Title>
        <Text className="text-gray-500">
          Facilities Management Overview - Real-time monitoring
        </Text>
      </div>

      {/* KPI Row */}
      <Grid numItems={1} numItemsSm={2} numItemsLg={4} className="gap-4 mb-6">
        <Col>
          <KPICard
            title="Total Sites"
            value={stats?.total_sites ?? 0}
            icon={<Building2 className="h-6 w-6 text-bidvest-blue-600" />}
            trend={`${normalSites} healthy`}
            trendColor="green"
          />
        </Col>
        <Col>
          <KPICard
            title="Equipment"
            value={stats?.total_equipment ?? 0}
            icon={<Cpu className="h-6 w-6 text-bidvest-blue-600" />}
            trend={`${stats?.uptime_percent ?? 0}% uptime`}
            trendColor="green"
          />
        </Col>
        <Col>
          <KPICard
            title="Active Alerts"
            value={stats?.active_alerts ?? 0}
            icon={<Bell className="h-6 w-6 text-amber-500" />}
            trend={criticalAlerts > 0 ? `${criticalAlerts} critical` : "None critical"}
            trendColor={criticalAlerts > 0 ? "red" : "green"}
          />
        </Col>
        <Col>
          <KPICard
            title="Anomalies Detected"
            value={stats?.pending_anomalies ?? 0}
            icon={<TrendingUp className="h-6 w-6 text-purple-500" />}
            trend="AI predictions"
            trendColor="gray"
          />
        </Col>
      </Grid>

      {/* Main Content Grid */}
      <Grid numItems={1} numItemsLg={2} className="gap-6">
        {/* Left Column - Site Overview */}
        <Col>
          <Card className="h-full">
            <Title className="mb-4">Site Overview</Title>
            <div className="space-y-3">
              {sites.length === 0 ? (
                <Text className="text-gray-400">No sites available</Text>
              ) : (
                sites.slice(0, 5).map((site) => (
                  <div
                    key={site.id}
                    className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <Building2 className="h-5 w-5 text-gray-400" />
                      <div>
                        <Text className="font-medium text-gray-900">
                          {site.name}
                        </Text>
                        <Text className="text-sm text-gray-500">
                          {site.location} · {site.equipment_count} equipment
                        </Text>
                      </div>
                    </div>
                    <Badge
                      color={
                        site.status === "normal"
                          ? "green"
                          : site.status === "warning"
                          ? "yellow"
                          : "red"
                      }
                      size="sm"
                    >
                      {site.status}
                    </Badge>
                  </div>
                ))
              )}
              {sites.length > 5 && (
                <Text className="text-center text-gray-400 text-sm pt-2">
                  +{sites.length - 5} more sites
                </Text>
              )}
            </div>
          </Card>
        </Col>

        {/* Right Column - Alerts Feed */}
        <Col>
          <Card className="h-full">
            <Flex justifyContent="between" alignItems="center" className="mb-4">
              <Title>Recent Alerts</Title>
              {criticalAlerts > 0 && (
                <Badge color="red" size="sm">
                  {criticalAlerts} critical
                </Badge>
              )}
            </Flex>
            <div className="space-y-3">
              {alerts.length === 0 ? (
                <div className="text-center py-8">
                  <Activity className="h-12 w-12 text-green-500 mx-auto mb-2" />
                  <Text className="text-gray-500">No active alerts</Text>
                </div>
              ) : (
                alerts.slice(0, 5).map((alert) => (
                  <div
                    key={alert.id}
                    className={`p-3 rounded-lg border-l-4 ${
                      alert.severity === "critical"
                        ? "bg-red-50 border-red-500"
                        : alert.severity === "high"
                        ? "bg-orange-50 border-orange-500"
                        : alert.severity === "medium"
                        ? "bg-yellow-50 border-yellow-500"
                        : "bg-gray-50 border-gray-300"
                    }`}
                  >
                    <Flex justifyContent="between" alignItems="start">
                      <div className="flex-1">
                        <Text className="font-medium text-gray-900">
                          {alert.message}
                        </Text>
                        <Text className="text-sm text-gray-500">
                          {alert.site_name} · {alert.equipment_name}
                        </Text>
                      </div>
                      <Badge
                        color={
                          alert.severity === "critical"
                            ? "red"
                            : alert.severity === "high"
                            ? "orange"
                            : alert.severity === "medium"
                            ? "yellow"
                            : "gray"
                        }
                        size="sm"
                      >
                        {alert.severity}
                      </Badge>
                    </Flex>
                  </div>
                ))
              )}
              {alerts.length > 5 && (
                <Text className="text-center text-gray-400 text-sm pt-2">
                  +{alerts.length - 5} more alerts
                </Text>
              )}
            </div>
          </Card>
        </Col>
      </Grid>

      {/* Bottom Area - Anomalies / Charts Placeholder */}
      <div className="mt-6">
        <Card>
          <Title className="mb-4">AI Predictions & Anomalies</Title>
          <div className="space-y-3">
            {anomalies.length === 0 ? (
              <div className="text-center py-8">
                <TrendingUp className="h-12 w-12 text-gray-300 mx-auto mb-2" />
                <Text className="text-gray-500">No anomalies predicted</Text>
              </div>
            ) : (
              <Grid numItems={1} numItemsMd={2} numItemsLg={3} className="gap-4">
                {anomalies.slice(0, 3).map((anomaly) => (
                  <Col key={anomaly.id}>
                    <div className="p-4 bg-purple-50 rounded-lg border border-purple-100">
                      <Flex justifyContent="between" alignItems="start" className="mb-2">
                        <AlertTriangle className="h-5 w-5 text-purple-500" />
                        <Badge color="purple" size="sm">
                          {Math.round(anomaly.confidence * 100)}% confidence
                        </Badge>
                      </Flex>
                      <Text className="font-medium text-gray-900 mb-1">
                        {anomaly.prediction}
                      </Text>
                      <Text className="text-sm text-gray-500 mb-2">
                        {anomaly.site_name} · {anomaly.equipment_name}
                      </Text>
                      <Text className="text-xs text-purple-600">
                        Recommendation: {anomaly.recommendation}
                      </Text>
                    </div>
                  </Col>
                ))}
              </Grid>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}

export default Dashboard;
