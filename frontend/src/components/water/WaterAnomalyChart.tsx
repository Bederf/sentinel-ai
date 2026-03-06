/**
 * WaterAnomalyChart - Water flow anomaly visualization with threshold indicators
 *
 * Displays:
 * - Line chart of flow rate over time
 * - Baseline (mean) line
 * - Warning threshold (baseline + 2*std_dev)
 * - Critical threshold (baseline + 3*std_dev)
 * - Detected anomalies highlighted
 * - Summary statistics
 */

import { useState } from "react";
import {
  Text,
  Flex,
  LineChart,
} from "@tremor/react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";

interface AnomalyData {
  timestamp: string;
  flow_rate_lpm: number;
  is_anomaly: boolean;
  anomaly_type?: "night_flow" | "statistical_anomaly" | "spike";
  severity?: "warning" | "critical";
}

interface AnomalyHistory {
  zone_id: string;
  days: number;
  data: AnomalyData[];
  baseline_flow_lpm: number;
  std_dev_lpm: number;
  warning_threshold_lpm: number;
  critical_threshold_lpm: number;
  min_observed_lpm: number;
  max_observed_lpm: number;
  anomaly_count: number;
  warning_count: number;
  critical_count: number;
}

interface WaterAnomalyChartProps {
  zoneId: string;
  days?: number;
}

export const WaterAnomalyChart: React.FC<WaterAnomalyChartProps> = ({
  zoneId,
  days = 7,
}) => {
  const [timeRange, setTimeRange] = useState<"24h" | "7d" | "30d">("7d");

  // Mock anomaly history data
  const { data: anomalies, isLoading } = useQuery({
    queryKey: ["water", "anomaly", zoneId, timeRange],
    queryFn: async () => {
      const mockHistory: AnomalyHistory = {
        zone_id: zoneId,
        days: 7,
        data: generateMockAnomalyData(7),
        baseline_flow_lpm: 12.5,
        std_dev_lpm: 3.2,
        warning_threshold_lpm: 18.9,
        critical_threshold_lpm: 22.1,
        min_observed_lpm: 0.5,
        max_observed_lpm: 45.0,
        anomaly_count: 3,
        warning_count: 2,
        critical_count: 1,
      };
      return mockHistory;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  if (isLoading || !anomalies) {
    return (
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <div className="flex items-center justify-center h-64">
          <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Loading anomaly data...
          </Text>
        </div>
      </div>
    );
  }

  // Prepare chart data with threshold lines
  const chartData = anomalies.data.map((d) => {
    const date = new Date(d.timestamp);
    return {
      time: date.toLocaleTimeString("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }),
      "Flow Rate": Math.round(d.flow_rate_lpm * 10) / 10,
      Baseline: Math.round(anomalies.baseline_flow_lpm * 10) / 10,
      "Warning (2σ)": Math.round(anomalies.warning_threshold_lpm * 10) / 10,
      "Critical (3σ)": Math.round(anomalies.critical_threshold_lpm * 10) / 10,
    };
  });

  return (
    <div className="space-y-6">
      {/* Time Range Selector */}
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <Flex justifyContent="between" alignItems="center">
          <h4 className="font-medium text-base" style={{ color: "var(--color-sentinel-text-primary)" }}>Flow Rate Anomaly Detection</h4>
          <div className="flex gap-2">
            {(["24h", "7d", "30d"] as const).map((range) => (
              <button
                key={range}
                onClick={() => setTimeRange(range)}
                className="text-xs px-2 py-1 rounded"
                style={{
                  background:
                    timeRange === range
                      ? "var(--color-sentinel-blue)"
                      : "var(--color-sentinel-bg-secondary)",
                  color:
                    timeRange === range
                      ? "white"
                      : "var(--color-sentinel-text-secondary)",
                }}
              >
                {range === "24h" ? "24h" : range === "7d" ? "7 days" : "30 days"}
              </button>
            ))}
          </div>
        </Flex>
      </div>

      {/* Main Chart */}
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <Text className="text-xs mb-4" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Flow rate in liters per minute with baseline and threshold indicators
        </Text>
        {chartData.length > 0 ? (
          <LineChart
            data={chartData}
            index="time"
            categories={[
              "Flow Rate",
              "Baseline",
              "Warning (2σ)",
              "Critical (3σ)",
            ]}
            colors={["blue", "green", "yellow", "red"]}
            showLegend={true}
          />
        ) : (
          <div className="h-64 flex items-center justify-center">
            <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>
              No data available
            </Text>
          </div>
        )}
      </div>

      {/* Statistics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
          <Text
            style={{ color: "var(--color-sentinel-text-secondary)" }}
            className="text-xs"
          >
            Mean Flow Rate
          </Text>
          <p className="text-xl font-semibold mt-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
            {anomalies.baseline_flow_lpm.toFixed(1)} LPM
          </p>
          <Text className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Baseline (standard deviation: {anomalies.std_dev_lpm.toFixed(2)})
          </Text>
        </div>

        <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
          <Text
            style={{ color: "var(--color-sentinel-text-secondary)" }}
            className="text-xs"
          >
            Observed Range
          </Text>
          <p className="text-xl font-semibold mt-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
            {anomalies.min_observed_lpm.toFixed(1)} - {anomalies.max_observed_lpm.toFixed(1)} LPM
          </p>
          <Text className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Min / Max in period
          </Text>
        </div>

        <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
          <Text
            style={{ color: "var(--color-sentinel-text-secondary)" }}
            className="text-xs"
          >
            Anomalies Detected
          </Text>
          <p className="text-xl font-semibold mt-2" style={{ color: "var(--color-sentinel-text-primary)" }}>{anomalies.anomaly_count}</p>
          <Text className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            {anomalies.warning_count} warning, {anomalies.critical_count} critical
          </Text>
        </div>
      </div>

      {/* Threshold Information */}
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <h4 className="font-medium text-base mb-4" style={{ color: "var(--color-sentinel-text-primary)" }}>Threshold Configuration</h4>
        <div className="space-y-3">
          <div className="flex items-center justify-between p-3 rounded" style={{background: "rgba(34, 197, 94, 0.1)"}}>
            <div>
              <Text className="font-semibold">Baseline (Mean)</Text>
              <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Normal operating flow
              </Text>
            </div>
            <Text className="font-semibold text-lg">
              {anomalies.baseline_flow_lpm.toFixed(1)} LPM
            </Text>
          </div>

          <div className="flex items-center justify-between p-3 rounded" style={{background: "rgba(251, 146, 60, 0.1)"}}>
            <div>
              <Text className="font-semibold">Warning Threshold (μ + 2σ)</Text>
              <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Elevated flow detected
              </Text>
            </div>
            <Text className="font-semibold text-lg">
              {anomalies.warning_threshold_lpm.toFixed(1)} LPM
            </Text>
          </div>

          <div className="flex items-center justify-between p-3 rounded" style={{background: "rgba(239, 68, 68, 0.1)"}}>
            <div>
              <Text className="font-semibold">Critical Threshold (μ + 3σ)</Text>
              <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Severe anomaly - likely leak
              </Text>
            </div>
            <Text className="font-semibold text-lg">
              {anomalies.critical_threshold_lpm.toFixed(1)} LPM
            </Text>
          </div>
        </div>
      </div>

      {/* Detected Anomalies List */}
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <h4 className="font-medium text-base mb-4" style={{ color: "var(--color-sentinel-text-primary)" }}>Detected Anomalies</h4>
        {anomalies.data.filter((d) => d.is_anomaly).length === 0 ? (
          <div className="text-center py-6">
            <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>
              No anomalies detected
            </Text>
          </div>
        ) : (
          <div className="space-y-2">
            {anomalies.data
              .filter((d) => d.is_anomaly)
              .map((anomaly, idx) => {
                const date = new Date(anomaly.timestamp);
                const severityColor =
                  anomaly.severity === "critical"
                    ? "bg-red-50 dark:bg-red-950"
                    : "bg-yellow-50 dark:bg-yellow-950";

                return (
                  <div
                    key={idx}
                    className={`p-3 rounded border ${severityColor}`}
                    style={{
                      borderColor:
                        anomaly.severity === "critical"
                          ? "rgba(239, 68, 68, 0.3)"
                          : "rgba(251, 146, 60, 0.3)",
                    }}
                  >
                    <Flex justifyContent="between" alignItems="start">
                      <div className="flex gap-2">
                        <AlertTriangle
                          className="h-4 w-4 mt-0.5"
                          style={{
                            color:
                              anomaly.severity === "critical"
                                ? "#ef4444"
                                : "#f59e0b",
                          }}
                        />
                        <div>
                          <Text className="font-semibold text-sm">
                            {anomaly.anomaly_type?.replace(/_/g, " ") || "Anomaly"}
                          </Text>
                          <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                            {date.toLocaleString()}
                          </Text>
                        </div>
                      </div>
                      <div className="text-right">
                        <Text className="font-semibold">
                          {anomaly.flow_rate_lpm.toFixed(1)} LPM
                        </Text>
                        <Text
                          className="text-xs"
                          style={{
                            color:
                              anomaly.severity === "critical"
                                ? "#ef4444"
                                : "#f59e0b",
                          }}
                        >
                          {anomaly.severity?.toUpperCase()}
                        </Text>
                      </div>
                    </Flex>
                  </div>
                );
              })}
          </div>
        )}
      </div>
    </div>
  );
};

// Helper to generate mock anomaly data
function generateMockAnomalyData(days: number): AnomalyData[] {
  const data: AnomalyData[] = [];
  const baseline = 12.5;
  const stdDev = 3.2;

  for (let d = 0; d < days; d++) {
    for (let h = 0; h < 24; h += 3) {
      const date = new Date();
      date.setDate(date.getDate() - (days - d));
      date.setHours(h, 0, 0, 0);

      // Generate normal data with some anomalies
      let flowRate = baseline + (Math.random() - 0.5) * stdDev * 2;

      // Inject some anomalies
      const rand = Math.random();
      let isAnomaly = false;
      let anomalyType: "night_flow" | "statistical_anomaly" | "spike" | undefined =
        undefined;
      let severity: "warning" | "critical" | undefined = undefined;

      if (h >= 22 || h <= 6) {
        // Night hours - night flow anomaly
        if (rand < 0.1) {
          isAnomaly = true;
          anomalyType = "night_flow";
          flowRate = baseline + stdDev * 2.5;
          severity = "warning";
        }
      }

      // Statistical anomaly
      if (rand < 0.05 && !isAnomaly) {
        isAnomaly = true;
        anomalyType = "statistical_anomaly";
        flowRate = baseline + stdDev * 2.8;
        severity = "warning";
      }

      // Spike (critical)
      if (rand < 0.02 && !isAnomaly) {
        isAnomaly = true;
        anomalyType = "spike";
        flowRate = baseline + stdDev * 3.5;
        severity = "critical";
      }

      data.push({
        timestamp: date.toISOString(),
        flow_rate_lpm: Math.max(0, flowRate),
        is_anomaly: isAnomaly,
        anomaly_type: anomalyType,
        severity: severity,
      });
    }
  }

  return data;
}
