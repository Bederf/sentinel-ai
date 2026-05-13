import { useState } from "react";
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
  days: _days = 7,
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
          <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Loading anomaly data...
          </span>
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

  const maxFlow = Math.max(
    ...chartData.map(d => Math.max(d["Flow Rate"], d["Critical (3σ)"]))
  );
  const maxBar = maxFlow > 0 ? maxFlow : 1;

  return (
    <div className="space-y-6">
      {/* Time Range Selector */}
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <div className="flex items-center justify-between">
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
        </div>
      </div>

      {/* Main Chart */}
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <span className="text-xs mb-4 block" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Flow rate in liters per minute with baseline and threshold indicators
        </span>
        {chartData.length > 0 ? (
          <div className="mt-4">
            {/* Threshold indicators */}
            <div className="flex items-center gap-4 mb-4 text-xs flex-wrap">
              <div className="flex items-center gap-1">
                <span className="w-3 h-0.5 rounded block" style={{ background: "#3b82f6" }} />
                <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Flow Rate</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-3 h-0.5 rounded block" style={{ background: "#22c55e" }} />
                <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Baseline</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-3 h-0.5 rounded block" style={{ background: "#eab308" }} />
                <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Warning (2σ)</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-3 h-0.5 rounded block" style={{ background: "#ef4444" }} />
                <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Critical (3σ)</span>
              </div>
            </div>

            {/* Bar chart showing flow rate with thresholds */}
            <div className="space-y-1">
              {chartData.slice(0, 40).map((item, i) => {
                const flowPct = (item["Flow Rate"] / maxBar) * 100;
                const baselinePct = (item.Baseline / maxBar) * 100;
                const warningPct = (item["Warning (2σ)"] / maxBar) * 100;
                const criticalPct = (item["Critical (3σ)"] / maxBar) * 100;
                return (
                  <div key={i} className="flex items-center gap-2">
                    <span className="text-xs w-20 shrink-0 text-right truncate" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      {item.time}
                    </span>
                    <div className="flex-grow relative h-5">
                      {/* Background container */}
                      <div className="absolute inset-0 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                        {/* Critical threshold line */}
                        <div
                          className="absolute top-0 w-0.5 h-full"
                          style={{
                            left: `${criticalPct}%`,
                            background: "#ef4444",
                            opacity: 0.7,
                          }}
                        />
                        {/* Warning threshold line */}
                        <div
                          className="absolute top-0 w-0.5 h-full"
                          style={{
                            left: `${warningPct}%`,
                            background: "#eab308",
                            opacity: 0.7,
                          }}
                        />
                        {/* Baseline line */}
                        <div
                          className="absolute top-0 w-0.5 h-full"
                          style={{
                            left: `${baselinePct}%`,
                            background: "#22c55e",
                            opacity: 0.7,
                          }}
                        />
                        {/* Flow rate bar */}
                        <div
                          className="absolute bottom-0 rounded-t-sm transition-all"
                          style={{
                            left: 0,
                            width: `${Math.max(flowPct, 1)}%`,
                            height: "100%",
                            background: item["Flow Rate"] >= item["Critical (3σ)"]
                              ? "#ef4444"
                              : item["Flow Rate"] >= item["Warning (2σ)"]
                              ? "#eab308"
                              : "#3b82f6",
                            opacity: 0.7,
                          }}
                        />
                      </div>
                    </div>
                    <span className="text-xs w-14 text-right font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {item["Flow Rate"]}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="h-64 flex items-center justify-center">
            <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
              No data available
            </span>
          </div>
        )}
      </div>

      {/* Statistics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
          <span
            style={{ color: "var(--color-sentinel-text-secondary)" }}
            className="text-xs"
          >
            Mean Flow Rate
          </span>
          <p className="text-xl font-semibold mt-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
            {anomalies.baseline_flow_lpm.toFixed(1)} LPM
          </p>
          <span className="text-xs mt-1 block" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Baseline (standard deviation: {anomalies.std_dev_lpm.toFixed(2)})
          </span>
        </div>

        <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
          <span
            style={{ color: "var(--color-sentinel-text-secondary)" }}
            className="text-xs"
          >
            Observed Range
          </span>
          <p className="text-xl font-semibold mt-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
            {anomalies.min_observed_lpm.toFixed(1)} - {anomalies.max_observed_lpm.toFixed(1)} LPM
          </p>
          <span className="text-xs mt-1 block" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Min / Max in period
          </span>
        </div>

        <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
          <span
            style={{ color: "var(--color-sentinel-text-secondary)" }}
            className="text-xs"
          >
            Anomalies Detected
          </span>
          <p className="text-xl font-semibold mt-2" style={{ color: "var(--color-sentinel-text-primary)" }}>{anomalies.anomaly_count}</p>
          <span className="text-xs mt-1 block" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            {anomalies.warning_count} warning, {anomalies.critical_count} critical
          </span>
        </div>
      </div>

      {/* Threshold Information */}
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <h4 className="font-medium text-base mb-4" style={{ color: "var(--color-sentinel-text-primary)" }}>Threshold Configuration</h4>
        <div className="space-y-3">
          <div className="flex items-center justify-between p-3 rounded" style={{background: "rgba(34, 197, 94, 0.1)"}}>
            <div>
              <p className="font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Baseline (Mean)</p>
              <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Normal operating flow
              </span>
            </div>
            <p className="font-semibold text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>
              {anomalies.baseline_flow_lpm.toFixed(1)} LPM
            </p>
          </div>

          <div className="flex items-center justify-between p-3 rounded" style={{background: "rgba(251, 146, 60, 0.1)"}}>
            <div>
              <p className="font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Warning Threshold (μ + 2σ)</p>
              <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Elevated flow detected
              </span>
            </div>
            <p className="font-semibold text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>
              {anomalies.warning_threshold_lpm.toFixed(1)} LPM
            </p>
          </div>

          <div className="flex items-center justify-between p-3 rounded" style={{background: "rgba(239, 68, 68, 0.1)"}}>
            <div>
              <p className="font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Critical Threshold (μ + 3σ)</p>
              <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Severe anomaly - likely leak
              </span>
            </div>
            <p className="font-semibold text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>
              {anomalies.critical_threshold_lpm.toFixed(1)} LPM
            </p>
          </div>
        </div>
      </div>

      {/* Detected Anomalies List */}
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <h4 className="font-medium text-base mb-4" style={{ color: "var(--color-sentinel-text-primary)" }}>Detected Anomalies</h4>
        {anomalies.data.filter((d) => d.is_anomaly).length === 0 ? (
          <div className="text-center py-6">
            <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
              No anomalies detected
            </span>
          </div>
        ) : (
          <div className="space-y-2">
            {anomalies.data
              .filter((d) => d.is_anomaly)
              .map((anomaly, idx) => {
                const date = new Date(anomaly.timestamp);

                return (
                  <div
                    key={idx}
                    className="p-3 rounded border"
                    style={{
                      background:
                        anomaly.severity === "critical"
                          ? "rgba(239, 68, 68, 0.08)"
                          : "rgba(251, 146, 60, 0.08)",
                      borderColor:
                        anomaly.severity === "critical"
                          ? "rgba(239, 68, 68, 0.3)"
                          : "rgba(251, 146, 60, 0.3)",
                    }}
                  >
                    <div className="flex items-start justify-between">
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
                          <p className="font-semibold text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                            {anomaly.anomaly_type?.replace(/_/g, " ") || "Anomaly"}
                          </p>
                          <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                            {date.toLocaleString()}
                          </span>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                          {anomaly.flow_rate_lpm.toFixed(1)} LPM
                        </p>
                        <span
                          className="text-xs"
                          style={{
                            color:
                              anomaly.severity === "critical"
                                ? "#ef4444"
                                : "#f59e0b",
                          }}
                        >
                          {anomaly.severity?.toUpperCase()}
                        </span>
                      </div>
                    </div>
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
