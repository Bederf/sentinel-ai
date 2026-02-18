/**
 * CostValidationCard - Monthly Cost Reconciliation & Tariff Adjustment
 *
 * Displays:
 * - Simulated vs Real invoice costs
 * - Monthly variance % and R amount
 * - Tariff adjustment recommendation (±10% factor)
 * - Confidence score based on data consistency
 *
 * Used for validating energy + water cost calculations against actual bills.
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
  Button,
} from "@tremor/react";
import { DollarSign, AlertTriangle, TrendingUp } from "lucide-react";

interface CostValidation {
  period_start: string;
  period_end: string;
  simulated_cost_r: number;
  real_cost_r: number | null;
  variance_pct: number;
  recommendation: string;
  confidence: number;
  tariff_adjustment_factor: number;
}

interface CostValidationCardProps {
  buildingId?: string;
  className?: string;
}

export function CostValidationCard({
  buildingId = "S002",
  className = "",
}: CostValidationCardProps) {
  const [validation, setValidation] = useState<CostValidation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchValidation = async () => {
      try {
        setLoading(true);
        const response = await fetch(
          `/api/validation/cost/daily?site_id=${buildingId}`
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

    const interval = setInterval(fetchValidation, 60000); // Refresh every minute
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

  const varianceAbove5Pct = Math.abs(validation.variance_pct) > 5;
  const varianceAbove15Pct = Math.abs(validation.variance_pct) > 15;
  const adjustmentNeeded = Math.abs(validation.tariff_adjustment_factor - 1.0) > 0.02;

  const savingsR = validation.real_cost_r
    ? Math.abs(validation.real_cost_r - validation.simulated_cost_r)
    : null;

  return (
    <Card className={className}>
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2">
          <DollarSign className="w-5 h-5 text-green-400" />
          <Title className="text-lg">Cost Validation</Title>
        </div>
        {varianceAbove15Pct ? (
          <Badge variant="rose" className="text-xs">
            🔴 Critical (>{(validation.variance_pct).toFixed(1)}%)
          </Badge>
        ) : varianceAbove5Pct ? (
          <Badge variant="warning" className="text-xs">
            🟡 Warning (>{(validation.variance_pct).toFixed(1)}%)
          </Badge>
        ) : (
          <Badge variant="success" className="text-xs">
            ✓ OK
          </Badge>
        )}
      </div>

      <Grid numCols={2} gap="md" className="mb-4">
        {/* Simulated Cost */}
        <Col>
          <div className="bg-slate-700/50 rounded-lg p-3">
            <Text className="text-xs text-gray-400">Simulated Cost (Monthly)</Text>
            <div className="text-2xl font-bold text-white mt-1">
              R{validation.simulated_cost_r.toLocaleString("en-ZA", {
                maximumFractionDigits: 0,
              })}
            </div>
            <Text className="text-xs text-gray-500 mt-1">
              Energy + Water + Service
            </Text>
          </div>
        </Col>

        {/* Real Invoice */}
        <Col>
          <div className="bg-slate-700/50 rounded-lg p-3">
            <Text className="text-xs text-gray-400">Real Invoice</Text>
            {validation.real_cost_r ? (
              <>
                <div className="text-2xl font-bold text-white mt-1">
                  R{validation.real_cost_r.toLocaleString("en-ZA", {
                    maximumFractionDigits: 0,
                  })}
                </div>
                {savingsR && (
                  <Text className="text-xs text-gray-500 mt-1">
                    Variance: R{(savingsR).toLocaleString("en-ZA", {
                      maximumFractionDigits: 0,
                    })}
                  </Text>
                )}
              </>
            ) : (
              <Text className="text-xs text-gray-400 mt-1">
                Awaiting invoice upload
              </Text>
            )}
          </div>
        </Col>

        {/* Variance Analysis */}
        <Col>
          <div className="bg-slate-700/50 rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
              <Text className="text-xs text-gray-400">Variance %</Text>
              <TrendingUp className={`w-4 h-4 ${
                Math.abs(validation.variance_pct) < 5
                  ? "text-green-400"
                  : Math.abs(validation.variance_pct) < 15
                  ? "text-yellow-400"
                  : "text-red-400"
              }`} />
            </div>
            <div className="text-lg font-semibold text-white">
              {validation.variance_pct > 0 ? "+" : ""}
              {validation.variance_pct.toFixed(1)}%
            </div>
            <ProgressBar
              value={Math.min(100, Math.abs(validation.variance_pct))}
              color={
                Math.abs(validation.variance_pct) < 5
                  ? "green"
                  : Math.abs(validation.variance_pct) < 15
                  ? "yellow"
                  : "red"
              }
              className="mt-2"
            />
            <Text className="text-xs text-gray-500 mt-1">
              {Math.abs(validation.variance_pct) < 5
                ? "Within tolerance"
                : Math.abs(validation.variance_pct) < 15
                ? "Adjustment recommended"
                : "Out of range"}
            </Text>
          </div>
        </Col>

        {/* Tariff Adjustment */}
        <Col>
          <div className="bg-slate-700/50 rounded-lg p-3">
            <Text className="text-xs text-gray-400">Tariff Adjustment</Text>
            <div className="text-lg font-semibold text-white mt-1">
              {validation.tariff_adjustment_factor > 1
                ? "+"
                : ""}
              {((validation.tariff_adjustment_factor - 1) * 100).toFixed(1)}%
            </div>
            <ProgressBar
              value={validation.confidence * 100}
              color="blue"
              className="mt-2"
            />
            <Text className="text-xs text-gray-500 mt-1">
              Confidence: {(validation.confidence * 100).toFixed(0)}%
            </Text>
          </div>
        </Col>
      </Grid>

      {/* Recommendation */}
      {adjustmentNeeded && (
        <div className="bg-blue-900/20 border border-blue-700/30 rounded-lg p-3 mb-4">
          <Text className="text-sm font-semibold text-blue-300">
            Tariff Adjustment Recommended
          </Text>
          <Text className="text-xs text-blue-400/70 mt-1">
            {validation.recommendation}
          </Text>
          <Button
            className="mt-3 bg-blue-600 hover:bg-blue-700 text-white text-xs"
            size="sm"
          >
            Apply Adjustment
          </Button>
        </div>
      )}

      {/* Critical Warning */}
      {varianceAbove15Pct && (
        <div className="bg-rose-900/20 border border-rose-700/30 rounded-lg p-3 flex gap-3">
          <AlertTriangle className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5" />
          <div>
            <Text className="text-sm font-semibold text-rose-300">
              Investigate Cost Discrepancy
            </Text>
            <Text className="text-xs text-rose-400/70 mt-1">
              Monthly cost variance exceeds 15%. Check tariff rates, consumption data,
              and meter calibration.
            </Text>
          </div>
        </div>
      )}
    </Card>
  );
}
