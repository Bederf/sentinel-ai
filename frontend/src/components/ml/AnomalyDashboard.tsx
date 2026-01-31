/**
 * Anomaly Detection Dashboard
 *
 * Shows anomaly status for all monitored equipment with
 * severity indicators and score visualization.
 */

import { useEffect, useState } from "react";
import {
  Card,
  Title,
  Table,
  TableHead,
  TableHeaderCell,
  TableBody,
  TableRow,
  TableCell,
  Badge,
  ProgressBar,
  Flex,
  Text,
  Grid,
  Metric,
  Button,
  Icon,
} from "@tremor/react";
import {
  ExclamationTriangleIcon,
  CheckCircleIcon,
  ArrowPathIcon,
} from "@heroicons/react/24/outline";
import type { AnomalyResult, MLHealth } from "../../lib/mlApi";
import {
  getAllAnomalies,
  getAnomalyAlerts,
  getMLHealth,
  getSeverityColor,
  getSeverityBadge,
} from "../../lib/mlApi";

interface AnomalyDashboardProps {
  refreshInterval?: number;
}

export function AnomalyDashboard({ refreshInterval = 30000 }: AnomalyDashboardProps) {
  const [anomalies, setAnomalies] = useState<AnomalyResult[]>([]);
  const [alerts, setAlerts] = useState<AnomalyResult[]>([]);
  const [health, setHealth] = useState<MLHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const fetchData = async () => {
    try {
      setError(null);
      const [anomalyData, alertData, healthData] = await Promise.all([
        getAllAnomalies(20),
        getAnomalyAlerts(),
        getMLHealth(),
      ]);
      setAnomalies(anomalyData);
      setAlerts(alertData);
      setHealth(healthData);
      setLastRefresh(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();

    if (refreshInterval > 0) {
      const interval = setInterval(fetchData, refreshInterval);
      return () => clearInterval(interval);
    }
  }, [refreshInterval]);

  const normalCount = anomalies.filter((a) => !a.is_anomaly).length;
  const anomalyCount = anomalies.filter((a) => a.is_anomaly).length;

  if (loading) {
    return (
      <Card>
        <Title>Anomaly Detection Dashboard</Title>
        <div className="h-96 flex items-center justify-center">
          <Text>Loading anomaly data...</Text>
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <Grid numItems={1} numItemsSm={2} numItemsLg={4} className="gap-4">
        <Card decoration="top" decorationColor="green">
          <Flex justifyContent="start" className="space-x-4">
            <Icon icon={CheckCircleIcon} color="green" size="lg" />
            <div>
              <Text>Normal Equipment</Text>
              <Metric>{normalCount}</Metric>
            </div>
          </Flex>
        </Card>

        <Card decoration="top" decorationColor="red">
          <Flex justifyContent="start" className="space-x-4">
            <Icon icon={ExclamationTriangleIcon} color="red" size="lg" />
            <div>
              <Text>Active Anomalies</Text>
              <Metric>{anomalyCount}</Metric>
            </div>
          </Flex>
        </Card>

        <Card decoration="top" decorationColor="blue">
          <Text>Active Models</Text>
          <Metric>{health?.active_models || 0}</Metric>
          <Text className="text-sm text-gray-500">
            {health?.equipment_types_covered?.join(", ") || "None"}
          </Text>
        </Card>

        <Card decoration="top" decorationColor="gray">
          <Text>Last Updated</Text>
          <Metric className="text-lg">
            {lastRefresh.toLocaleTimeString()}
          </Metric>
          <Button
            size="xs"
            variant="secondary"
            icon={ArrowPathIcon}
            onClick={fetchData}
            className="mt-2"
          >
            Refresh
          </Button>
        </Card>
      </Grid>

      {/* Active Alerts */}
      {alerts.length > 0 && (
        <Card>
          <Title>Active Anomaly Alerts</Title>
          <Table className="mt-4">
            <TableHead>
              <TableRow>
                <TableHeaderCell>Equipment</TableHeaderCell>
                <TableHeaderCell>Type</TableHeaderCell>
                <TableHeaderCell>Severity</TableHeaderCell>
                <TableHeaderCell>Score</TableHeaderCell>
                <TableHeaderCell>Threshold</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {alerts.map((alert) => (
                <TableRow key={alert.equipment_id}>
                  <TableCell>
                    <Text className="font-medium">{alert.equipment_id}</Text>
                  </TableCell>
                  <TableCell>{alert.equipment_type}</TableCell>
                  <TableCell>
                    <Badge color={getSeverityColor(alert.severity) as any}>
                      {getSeverityBadge(alert.severity)}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Text>{alert.anomaly_score?.toFixed(6) || "N/A"}</Text>
                  </TableCell>
                  <TableCell>
                    <Text>{alert.threshold?.toFixed(6) || "N/A"}</Text>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      {/* All Equipment Status */}
      <Card>
        <Title>All Equipment Anomaly Status</Title>
        {error ? (
          <Text color="red" className="mt-4">
            {error}
          </Text>
        ) : (
          <Table className="mt-4">
            <TableHead>
              <TableRow>
                <TableHeaderCell>Equipment</TableHeaderCell>
                <TableHeaderCell>Type</TableHeaderCell>
                <TableHeaderCell>Status</TableHeaderCell>
                <TableHeaderCell>Score vs Threshold</TableHeaderCell>
                <TableHeaderCell>Severity</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {anomalies.map((item) => (
                <TableRow key={item.equipment_id}>
                  <TableCell>
                    <Text className="font-medium">{item.equipment_id}</Text>
                  </TableCell>
                  <TableCell>{item.equipment_type || "N/A"}</TableCell>
                  <TableCell>
                    {item.is_anomaly ? (
                      <Badge color="red">Anomaly</Badge>
                    ) : (
                      <Badge color="green">Normal</Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <Flex className="space-x-2">
                      <ProgressBar
                        value={Math.min(item.score_pct || 0, 100)}
                        color={
                          (item.score_pct || 0) > 100
                            ? "red"
                            : (item.score_pct || 0) > 70
                            ? "yellow"
                            : "green"
                        }
                        className="w-24"
                      />
                      <Text className="text-sm">
                        {item.score_pct?.toFixed(0) || 0}%
                      </Text>
                    </Flex>
                  </TableCell>
                  <TableCell>
                    <Badge color={getSeverityColor(item.severity) as any}>
                      {getSeverityBadge(item.severity)}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>
    </div>
  );
}

export default AnomalyDashboard;
