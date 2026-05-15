import { useState, useEffect } from "react";

import { AlertTriangle, Zap, TrendingDown } from "lucide-react";
import { authorizedFetch } from "@/lib/api";
import { Card } from "../Card";
import { Badge } from "../Badge";

interface PowerMeterValidationRaw {
  mean_kw?: number;
  stdev_kw?: number;
  min_kw?: number;
  max_kw?: number;
  baseline_mean?: number;
  baseline_stdev?: number;
  baseline_min?: number;
  baseline_max?: number;
  median_kw?: number;
  p95_kw?: number;
  samples?: number;
  lookback_days?: number;
  meter_id?: string;
  reading_kwh?: number;
  validation_status?: string;
  severity?: string;
  variance_pct?: number;
  cop_current?: number;
  cop_design?: number;
  anomaly_detected?: boolean;
  reason?: string;
}

interface PowerMeterValidation {
  baseline_mean: number;
  baseline_stdev: number;
  baseline_min?: number;
  baseline_max?: number;
  median_kw?: number;
  p95_kw?: number;
  samples?: number;
  lookback_days?: number;
  meter_id?: string;
  reading_kwh?: number;
  validation_status?: string;
  severity?: string;
  variance_pct?: number;
  cop_current?: number;
  cop_design?: number;
  anomaly_detected?: boolean;
  reason?: string;
}

function mapPowerMeterResponse(raw: PowerMeterValidationRaw): PowerMeterValidation {
  return {
    baseline_mean: raw.mean_kw ?? raw.baseline_mean ?? 0,
    baseline_stdev: raw.stdev_kw ?? raw.baseline_stdev ?? 0,
    baseline_min: raw.min_kw ?? raw.baseline_min,
    baseline_max: raw.max_kw ?? raw.baseline_max,
    median_kw: raw.median_kw,
    p95_kw: raw.p95_kw,
    samples: raw.samples,
    lookback_days: raw.lookback_days,
    meter_id: raw.meter_id,
    reading_kwh: raw.reading_kwh,
    validation_status: raw.validation_status,
    severity: raw.severity,
    variance_pct: raw.variance_pct,
    cop_current: raw.cop_current,
    cop_design: raw.cop_design,
    anomaly_detected: raw.anomaly_detected,
    reason: raw.reason,
  };
}

interface PowerMeterValidationCardProps {
  siteId?: string;
  className?: string;
}

export function PowerMeterValidationCard({
  siteId = "site-002",
  className = "",
}: PowerMeterValidationCardProps) {
  const [validation, setValidation] = useState<PowerMeterValidation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchValidation = async () => {
      try {
        setLoading(true);
        const response = await authorizedFetch(
          `/api/validation/power-meter/baseline?site_id=${siteId}`
        );
        if (!response.ok) throw new Error("Failed to fetch validation data");
        const data = await response.json();
        setValidation(mapPowerMeterResponse(data));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    };

    const interval = setInterval(fetchValidation, 30000);
    fetchValidation();

    return () => clearInterval(interval);
  }, [siteId]);

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

  if (validation.baseline_mean === undefined || validation.baseline_stdev === undefined) {
    return (
      <Card className={className}>
        <div className="bg-yellow-900/20 border border-yellow-700/30 rounded-lg p-4">
          <span className="text-yellow-300 text-sm">
            ⚠️ Power Meter Baseline data not yet available. Please ensure power meter data is being collected.
          </span>
        </div>
      </Card>
    );
  }

  const copPercent =
    validation.cop_current && validation.cop_design
      ? (validation.cop_current / validation.cop_design) * 100
      : 0;
  const isAnomalous = validation.anomaly_detected || false;
  const _isWarning = validation.severity === "warning";
  const isCritical = validation.severity === "critical";
  const _hasCurrentReading = validation.reading_kwh !== undefined;
  const hasCOPData =
    validation.cop_current !== undefined && validation.cop_design !== undefined;

  return (
    <Card className={className}>
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2">
          <Zap className="w-5 h-5 text-blue-400" />
          <h2 className="text-lg font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>Power Meter Validation</h2>
        </div>
        {isAnomalous && (
          <Badge
            style={{
              background: isCritical ? 'rgba(220, 38, 38, 0.15)' : 'rgba(245, 158, 11, 0.15)',
              color: isCritical ? 'var(--color-sentinel-red)' : 'var(--color-sentinel-amber)',
            }}
          >
            {isCritical ? "🔴 Critical" : "🟡 Anomaly"}
          </Badge>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <div className="bg-slate-700/50 rounded-lg p-3">
            <span className="text-xs text-gray-400">Mean Power</span>
            <div className="text-2xl font-bold text-white mt-1">
              {validation.baseline_mean.toFixed(1)} kW
            </div>
            <span className="text-xs text-gray-500 mt-1 block">
              Std Dev: ±{validation.baseline_stdev.toFixed(1)} kW
            </span>
          </div>
        </div>

        <div>
          <div className="bg-slate-700/50 rounded-lg p-3">
            <span className="text-xs text-gray-400">Statistics</span>
            <div className="text-sm font-semibold text-white mt-1">
              {validation.baseline_min !== undefined && validation.baseline_max !== undefined ? (
                <>Min: {validation.baseline_min.toFixed(1)} kW</>
              ) : (
                <>Samples: {validation.samples ?? 0}</>
              )}
            </div>
            {validation.p95_kw !== undefined && (
              <span className="text-xs text-gray-500 mt-1 block">
                P95: {validation.p95_kw.toFixed(1)} kW
              </span>
            )}
          </div>
        </div>

        {validation.baseline_min !== undefined && validation.baseline_max !== undefined && (
          <div>
            <div className="bg-slate-700/50 rounded-lg p-3">
              <span className="text-xs text-gray-400">Operating Range</span>
              <div className="text-lg font-semibold text-white mt-1">
                {validation.baseline_min.toFixed(1)} - {validation.baseline_max.toFixed(1)} kW
              </div>
              <span className="text-xs text-gray-500 mt-1 block">
                Lookback: {validation.lookback_days ?? 7} days
              </span>
            </div>
          </div>
        )}

        {hasCOPData && (
          <div>
            <div className="bg-slate-700/50 rounded-lg p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-400">COP Performance</span>
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
              <div className="w-full h-2 rounded-full mt-2 overflow-hidden" style={{ background: 'var(--color-sentinel-border)' }}>
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${Math.min(100, copPercent)}%`,
                    background: copPercent < 80
                      ? 'var(--color-sentinel-red)'
                      : copPercent < 90
                      ? 'var(--color-sentinel-amber)'
                      : 'var(--color-sentinel-green)',
                  }}
                />
              </div>
              <span className="text-xs text-gray-500 mt-1 block">
                {copPercent.toFixed(0)}% of Design
              </span>
            </div>
          </div>
        )}
      </div>

      {isAnomalous && (
        <div className="bg-rose-900/20 border border-rose-700/30 rounded-lg p-3 flex gap-3">
          <AlertTriangle className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5" />
          <div>
            <span className="text-sm font-semibold text-rose-300">
              Anomaly Detected
            </span>
            <span className="text-xs text-rose-400/70 mt-1 block">
              {validation.reason ||
                "Anomaly detected in power meter data. Review baseline statistics above."}
            </span>
          </div>
        </div>
      )}

      <div className="bg-blue-900/20 border border-blue-700/30 rounded-lg p-3 mt-4">
        <span className="text-xs text-blue-300">
          📊 Baseline Analysis: {validation.samples ?? 0} readings over{" "}
          {validation.lookback_days ?? 7} days
        </span>
      </div>
    </Card>
  );
}
