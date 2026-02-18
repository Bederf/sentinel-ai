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
  Col,
  ProgressBar,
} from "@tremor/react";
import { AlertTriangle, Zap, TrendingDown } from "lucide-react";

interface PowerMeterValidation {
  meter_id: string;
  reading_kwh: number;
  baseline_mean: number;
  baseline_stdev: number;
  baseline_min: number;
  baseline_max: number;
  validation_status: string;
  severity: string;
  variance_pct: number;
  cop_current: number;
  cop_design: number;
  anomaly_detected: boolean;
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
        const response = await fetch(
          `/api/validation/power-meter/baseline?site_id=${buildingId}`
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

  const copPercent = (validation.cop_current / validation.cop_design) * 100;
  const isAnomalous = validation.anomaly_detected;
  const isWarning = validation.severity === "warning";
  const isCritical = validation.severity === "critical";

  return (
    <Card className={className}>
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2">
          <Zap className="w-5 h-5 text-blue-400" />
          <Title className="text-lg">Power Meter Validation</Title>
        </div>
        {isAnomalous && (
          <Badge
            variant={isCritical ? "rose" : "warning"}
            className="text-xs"
          >
            {isCritical ? "🔴 Critical" : "🟡 Anomaly"}
          </Badge>
        )}
      </div>

      <Grid numCols={2} gap="md" className="mb-4">
        {/* Current Reading */}
        <Col>
          <div className="bg-slate-700/50 rounded-lg p-3">
            <Text className="text-xs text-gray-400">Current Reading</Text>
            <div className="text-2xl font-bold text-white mt-1">
              {validation.reading_kwh.toFixed(1)} kW
            </div>
            <Text className="text-xs text-gray-500 mt-1">
              Variance: {validation.variance_pct > 0 ? "+" : ""}
              {validation.variance_pct.toFixed(1)}%
            </Text>
          </div>
        </Col>

        {/* Baseline Stats */}
        <Col>
          <div className="bg-slate-700/50 rounded-lg p-3">
            <Text className="text-xs text-gray-400">Baseline (Mean ± SD)</Text>
            <div className="text-lg font-semibold text-white mt-1">
              {validation.baseline_mean.toFixed(1)} ± {validation.baseline_stdev.toFixed(1)} kW
            </div>
            <Text className="text-xs text-gray-500 mt-1">
              Range: {validation.baseline_min.toFixed(1)} - {validation.baseline_max.toFixed(1)} kW
            </Text>
          </div>
        </Col>

        {/* COP Performance */}
        <Col>
          <div className="bg-slate-700/50 rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
              <Text className="text-xs text-gray-400">COP Performance</Text>
              <TrendingDown className={`w-4 h-4 ${
                copPercent < 80 ? "text-red-400" : copPercent < 90 ? "text-yellow-400" : "text-green-400"
              }`} />
            </div>
            <div className="text-lg font-semibold text-white">
              {validation.cop_current.toFixed(2)} / {validation.cop_design.toFixed(2)}
            </div>
            <ProgressBar
              value={Math.min(100, copPercent)}
              color={copPercent < 80 ? "red" : copPercent < 90 ? "yellow" : "green"}
              className="mt-2"
            />
            <Text className="text-xs text-gray-500 mt-1">
              {copPercent.toFixed(0)}% of Design COP
            </Text>
          </div>
        </Col>

        {/* Status */}
        <Col>
          <div className="bg-slate-700/50 rounded-lg p-3">
            <Text className="text-xs text-gray-400">Validation Status</Text>
            <div className="mt-2">
              <Badge
                variant={
                  validation.validation_status === "ok"
                    ? "success"
                    : validation.validation_status === "warning"
                    ? "warning"
                    : "rose"
                }
              >
                {validation.validation_status.toUpperCase()}
              </Badge>
            </div>
            {validation.reason && (
              <Text className="text-xs text-gray-400 mt-2 italic">
                {validation.reason}
              </Text>
            )}
          </div>
        </Col>
      </Grid>

      {isAnomalous && (
        <div className="bg-rose-900/20 border border-rose-700/30 rounded-lg p-3 flex gap-3">
          <AlertTriangle className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5" />
          <div>
            <Text className="text-sm font-semibold text-rose-300">
              Anomaly Detected
            </Text>
            <Text className="text-xs text-rose-400/70 mt-1">
              Power consumption variance exceeds {validation.variance_pct > 25 ? "critical" : "warning"} threshold.
              {validation.cop_current < 2.9 && " COP degradation detected."}
            </Text>
          </div>
        </div>
      )}
    </Card>
  );
}
