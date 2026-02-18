/**
 * PowerMeterValidationCard - Real-time HVAC Power Anomaly Detection
 *
 * Displays:
 * - Baseline power statistics (mean, std dev, min/max)
 * - Current hourly power reading with Z-score anomaly detection
 * - COP (Coefficient of Performance) tracking vs design value
 * - Anomaly severity badge
 *
 * Used for validating simulated HVAC power against real meter data.
 */

import { useState, useEffect } from "react";
import {
  Card,
  Title,
  Text,
  Badge,
  Grid,
  ProgressBar,
} from "@tremor/react";
import { AlertTriangle, Zap, TrendingDown } from "lucide-react";

interface PowerMeterValidation {
  meter_id?: string;
  reading_kwh?: number;
  baseline_mean: number;
  baseline_stdev: number;
  baseline_min?: number;
  baseline_max?: number;
  median_kw?: number;
  p95_kw?: number;
  samples?: number;
  lookback_days?: number;
  validation_status?: string;
  severity?: string;
  variance_pct?: number;
  cop_current?: number;
  cop_design?: number;
  anomaly_detected?: boolean;
  reason?: string;
}

interface PowerMeterValidationCardProps {
  buildingId?: string;
  className?: string;
}

export function PowerMeterValidationCard({
  buildingId = "S002",
  className = "",
}: PowerMeterValidationCardProps) {
  const [validation, setValidation] = useState<PowerMeterValidation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchValidation = async () => {
      try {
        setLoading(true);
        const token = localStorage.getItem("sentinel_token");
        const response = await fetch(
          `/api/validation/power-meter/baseline?site_id=${buildingId}`,
          {
            headers: {
              Authorization: `Bearer ${token || ""}`,
              "Content-Type": "application/json",
            },
          }
        );
        if (!response.ok) throw new Error("Failed to fetch validation data");
        const data = await response.json();
        setValidation(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    };

    const interval = setInterval(fetchValidation, 30000); // Refresh every 30 seconds
    fetchValidation();

    return () => clearInterval(interval);
  }, [buildingId]);

  if (loading) {
    return (
      <Card className={className}>
        <div className="h-48 animate-pulse bg-gray-700 rounded" />
      </Card>
    );
  }

  if (error) {
    return (
      <Card className={className}>
        <div className="text-red-400 text-sm">{error}</div>
      </Card>
    );
  }

  if (!validation) return null;

  // Check if we have required baseline data
  if (validation.baseline_mean === undefined || validation.baseline_stdev === undefined) {
    return (
      <Card className={className}>
        <div className="bg-yellow-900/20 border border-yellow-700/30 rounded-lg p-4">
          <Text className="text-yellow-300 text-sm">
            ⚠️ Power Meter Baseline data not yet available. Please ensure power meter data is being collected.
          </Text>
        </div>
      </Card>
    );
  }

  const copPercent =
    validation.cop_current && validation.cop_design
      ? (validation.cop_current / validation.cop_design) * 100
      : 0;
  const isAnomalous = validation.anomaly_detected || false;
  const isWarning = validation.severity === "warning";
  const isCritical = validation.severity === "critical";
  const hasCurrentReading = validation.reading_kwh !== undefined;
  const hasCOPData =
    validation.cop_current !== undefined && validation.cop_design !== undefined;

  return (
    <Card className={className}>
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2">
          <Zap className="w-5 h-5 text-blue-400" />
          <Title className="text-lg">Power Meter Validation</Title>
        </div>
        {isAnomalous && (
          <Badge
            color={isCritical ? "rose" : "yellow"}
            className="text-xs"
          >
            {isCritical ? "🔴 Critical" : "🟡 Anomaly"}
          </Badge>
        )}
      </div>

      <Grid className="grid grid-cols-2 gap-4 mb-4">
        {/* Baseline Stats */}
        <div>
          <div className="bg-slate-700/50 rounded-lg p-3">
            <Text className="text-xs text-gray-400">Mean Power</Text>
            <div className="text-2xl font-bold text-white mt-1">
              {validation.baseline_mean.toFixed(1)} kW
            </div>
            <Text className="text-xs text-gray-500 mt-1">
              Std Dev: ±{validation.baseline_stdev.toFixed(1)} kW
            </Text>
          </div>
        </div>

        {/* Statistics */}
        <div>
          <div className="bg-slate-700/50 rounded-lg p-3">
            <Text className="text-xs text-gray-400">Statistics</Text>
            <div className="text-sm font-semibold text-white mt-1">
              {validation.baseline_min !== undefined && validation.baseline_max !== undefined ? (
                <>Min: {validation.baseline_min.toFixed(1)} kW</>
              ) : (
                <>Samples: {validation.samples ?? 0}</>
              )}
            </div>
            {validation.p95_kw !== undefined && (
              <Text className="text-xs text-gray-500 mt-1">
                P95: {validation.p95_kw.toFixed(1)} kW
              </Text>
            )}
          </div>
        </div>

        {/* Range Info */}
        {validation.baseline_min !== undefined && validation.baseline_max !== undefined && (
          <div>
            <div className="bg-slate-700/50 rounded-lg p-3">
              <Text className="text-xs text-gray-400">Operating Range</Text>
              <div className="text-lg font-semibold text-white mt-1">
                {validation.baseline_min.toFixed(1)} - {validation.baseline_max.toFixed(1)} kW
              </div>
              <Text className="text-xs text-gray-500 mt-1">
                Lookback: {validation.lookback_days ?? 7} days
              </Text>
            </div>
          </div>
        )}

        {/* COP Performance - only show if data exists */}
        {hasCOPData && (
          <div>
            <div className="bg-slate-700/50 rounded-lg p-3">
              <div className="flex items-center justify-between mb-2">
                <Text className="text-xs text-gray-400">COP Performance</Text>
                <TrendingDown
                  className={`w-4 h-4 ${
                    copPercent < 80
                      ? "text-red-400"
                      : copPercent < 90
                      ? "text-yellow-400"
                      : "text-green-400"
                  }`}
                />
              </div>
              <div className="text-lg font-semibold text-white">
                {validation.cop_current?.toFixed(2)} / {validation.cop_design?.toFixed(2)}
              </div>
              <ProgressBar
                value={Math.min(100, copPercent)}
                color={copPercent < 80 ? "red" : copPercent < 90 ? "yellow" : "green"}
                className="mt-2"
              />
              <Text className="text-xs text-gray-500 mt-1">
                {copPercent.toFixed(0)}% of Design
              </Text>
            </div>
          </div>
        )}
      </Grid>

      {isAnomalous && (
        <div className="bg-rose-900/20 border border-rose-700/30 rounded-lg p-3 flex gap-3">
          <AlertTriangle className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5" />
          <div>
            <Text className="text-sm font-semibold text-rose-300">
              Anomaly Detected
            </Text>
            <Text className="text-xs text-rose-400/70 mt-1">
              {validation.reason ||
                "Anomaly detected in power meter data. Review baseline statistics above."}
            </Text>
          </div>
        </div>
      )}

      {/* Info Message for Baseline Data */}
      <div className="bg-blue-900/20 border border-blue-700/30 rounded-lg p-3 mt-4">
        <Text className="text-xs text-blue-300">
          📊 Baseline Analysis: {validation.samples ?? 0} readings over{" "}
          {validation.lookback_days ?? 7} days
        </Text>
      </div>
    </Card>
  );
}
