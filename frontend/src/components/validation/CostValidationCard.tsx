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

import { useState, useEffect, useRef } from "react";
import {
  Card,
  Title,
  Text,
  Badge,
  Grid,
  ProgressBar,
  Button,
} from "@tremor/react";
import { DollarSign, AlertTriangle, TrendingUp, Upload, FileText, Loader2, CheckCircle } from "lucide-react";

interface CostValidationRaw {
  // API field names
  date?: string;
  energy_kwh?: number;
  water_liters?: number;
  energy_cost_r?: number;
  water_cost_r?: number;
  total_cost_r?: number;
  season?: string;
  // Extended fields (when available)
  period_start?: string;
  period_end?: string;
  simulated_cost_r?: number;
  real_cost_r?: number | null;
  variance_pct?: number;
  recommendation?: string;
  confidence?: number;
  tariff_adjustment_factor?: number;
  [key: string]: any;
}

interface CostValidation {
  period_start?: string;
  period_end?: string;
  simulated_cost_r?: number;
  real_cost_r?: number | null;
  variance_pct?: number;
  recommendation?: string;
  confidence?: number;
  tariff_adjustment_factor?: number;
  energy_kwh?: number;
  water_liters?: number;
  energy_cost_r?: number;
  water_cost_r?: number;
  season?: string;
}

/** Map API response fields to component fields */
function mapCostResponse(raw: CostValidationRaw): CostValidation {
  return {
    period_start: raw.period_start ?? raw.date,
    period_end: raw.period_end ?? raw.date,
    simulated_cost_r: raw.simulated_cost_r ?? raw.total_cost_r,
    real_cost_r: raw.real_cost_r ?? null,
    variance_pct: raw.variance_pct,
    recommendation: raw.recommendation,
    confidence: raw.confidence,
    tariff_adjustment_factor: raw.tariff_adjustment_factor,
    energy_kwh: raw.energy_kwh,
    water_liters: raw.water_liters,
    energy_cost_r: raw.energy_cost_r,
    water_cost_r: raw.water_cost_r,
    season: raw.season,
  };
}

interface CostValidationCardProps {
  siteId?: string;
  className?: string;
}

export function CostValidationCard({
  siteId = "S002",
  className = "",
}: CostValidationCardProps) {
  const [validation, setValidation] = useState<CostValidation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Invoice upload state
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{
    success: boolean;
    total_zar?: number;
    invoice_number?: string;
    message?: string;
  } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleInvoiceUpload = async (file: File) => {
    if (file.type !== "application/pdf") {
      setUploadResult({ success: false, message: "Only PDF files are supported" });
      return;
    }

    setUploading(true);
    setUploadResult(null);

    try {
      const token = localStorage.getItem("sentinel_token");
      const formData = new FormData();
      formData.append("file", file);
      formData.append("site_id", siteId);
      formData.append("municipality", "city_power");
      formData.append("utility_type", "electricity");
      formData.append("account_number", `${siteId}-MAIN`);

      const response = await fetch("/api/municipal-billing/invoices/upload", {
        method: "POST",
        headers: { Authorization: `Bearer ${token || ""}` },
        body: formData,
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || "Upload failed");
      }

      const data = await response.json();
      const invoice = data.invoice || {};
      const totalZar = invoice.total_amount_zar;
      const invoiceNumber = invoice.invoice_number || "Uploaded";

      setUploadResult({
        success: true,
        total_zar: totalZar,
        invoice_number: invoiceNumber,
      });

      // If we got a total from the PDF, run reconciliation
      if (totalZar && totalZar > 0) {
        const now = new Date();
        const reconResponse = await fetch(
          `/api/validation/cost?site_id=${siteId}&month=${now.getMonth() + 1}&year=${now.getFullYear()}&real_invoice_cost_r=${totalZar}`,
          {
            method: "POST",
            headers: {
              Authorization: `Bearer ${token || ""}`,
              "Content-Type": "application/json",
            },
          }
        );

        if (reconResponse.ok) {
          const reconData = await reconResponse.json();
          setValidation((prev) => prev ? {
            ...prev,
            real_cost_r: totalZar,
            variance_pct: reconData.variance_pct,
            recommendation: reconData.recommendation,
            tariff_adjustment_factor: reconData.tariff_adjustment_factor,
            confidence: reconData.confidence,
          } : prev);
        }
      }
    } catch (err) {
      setUploadResult({
        success: false,
        message: err instanceof Error ? err.message : "Upload failed",
      });
    } finally {
      setUploading(false);
    }
  };

  useEffect(() => {
    const fetchValidation = async () => {
      try {
        setLoading(true);
        const token = localStorage.getItem("sentinel_token");
        const response = await fetch(
          `/api/validation/cost/daily?site_id=${siteId}`,
          {
            headers: {
              Authorization: `Bearer ${token || ""}`,
              "Content-Type": "application/json",
            },
          }
        );
        if (!response.ok) throw new Error("Failed to fetch validation data");
        const data = await response.json();
        setValidation(mapCostResponse(data));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    };

    const interval = setInterval(fetchValidation, 60000); // Refresh every minute
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

  // Check if we have at least simulated cost data
  if (validation.simulated_cost_r === undefined) {
    return (
      <Card className={className}>
        <div className="bg-yellow-900/20 border border-yellow-700/30 rounded-lg p-4">
          <Text className="text-yellow-300 text-sm">
            ⚠️ Cost Validation data not yet available. Please ensure building energy data is being collected.
          </Text>
        </div>
      </Card>
    );
  }

  const varianceAbove5Pct =
    validation.variance_pct !== undefined && Math.abs(validation.variance_pct) > 5;
  const varianceAbove15Pct =
    validation.variance_pct !== undefined && Math.abs(validation.variance_pct) > 15;
  const adjustmentNeeded =
    validation.tariff_adjustment_factor !== undefined &&
    Math.abs(validation.tariff_adjustment_factor - 1.0) > 0.02;

  const savingsR =
    validation.real_cost_r !== undefined &&
    validation.real_cost_r !== null &&
    validation.simulated_cost_r !== undefined
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
          <Badge color="rose" className="text-xs">
            🔴 Critical ({Math.abs(validation.variance_pct ?? 0).toFixed(1)}%)
          </Badge>
        ) : varianceAbove5Pct ? (
          <Badge color="yellow" className="text-xs">
            🟡 Warning ({Math.abs(validation.variance_pct ?? 0).toFixed(1)}%)
          </Badge>
        ) : (
          <Badge color="green" className="text-xs">
            ✓ OK
          </Badge>
        )}
      </div>

      <Grid className="grid grid-cols-2 gap-4 mb-4">
        {/* Simulated Cost */}
        <div>
          <div className="bg-slate-700/50 rounded-lg p-3">
            <Text className="text-xs text-gray-400">Simulated Cost</Text>
            <div className="text-2xl font-bold text-white mt-1">
              {validation.simulated_cost_r !== undefined
                ? `R${validation.simulated_cost_r.toLocaleString("en-ZA", {
                    maximumFractionDigits: 0,
                  })}`
                : "—"}
            </div>
            <Text className="text-xs text-gray-500 mt-1">
              {validation.energy_cost_r !== undefined && validation.water_cost_r !== undefined
                ? `Energy R${validation.energy_cost_r.toLocaleString("en-ZA", { maximumFractionDigits: 0 })} + Water R${validation.water_cost_r.toLocaleString("en-ZA", { maximumFractionDigits: 0 })}`
                : "Energy + Water + Service"}
            </Text>
          </div>
        </div>

        {/* Real Invoice */}
        <div>
          <div className="bg-slate-700/50 rounded-lg p-3">
            <Text className="text-xs text-gray-400">Real Invoice</Text>
            {validation.real_cost_r !== undefined && validation.real_cost_r !== null ? (
              <>
                <div className="text-2xl font-bold text-white mt-1">
                  R{validation.real_cost_r.toLocaleString("en-ZA", {
                    maximumFractionDigits: 0,
                  })}
                </div>
                {savingsR !== null && (
                  <Text className="text-xs text-gray-500 mt-1">
                    Variance: R{savingsR.toLocaleString("en-ZA", {
                      maximumFractionDigits: 0,
                    })}
                  </Text>
                )}
              </>
            ) : (
              <div className="mt-1">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="application/pdf"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleInvoiceUpload(file);
                    e.target.value = "";
                  }}
                />
                {uploading ? (
                  <div className="flex items-center gap-2 mt-2">
                    <Loader2 className="w-4 h-4 text-amber-400 animate-spin" />
                    <Text className="text-xs text-amber-300">Analysing PDF...</Text>
                  </div>
                ) : uploadResult?.success ? (
                  <div className="flex items-center gap-2 mt-2">
                    <CheckCircle className="w-4 h-4 text-green-400" />
                    <Text className="text-xs text-green-300">
                      {uploadResult.total_zar
                        ? `R${uploadResult.total_zar.toLocaleString("en-ZA", { maximumFractionDigits: 0 })} extracted`
                        : "Uploaded — awaiting OCR"}
                    </Text>
                  </div>
                ) : uploadResult && !uploadResult.success ? (
                  <div>
                    <Text className="text-xs text-red-400 mt-1">{uploadResult.message}</Text>
                    <button
                      onClick={() => { setUploadResult(null); fileInputRef.current?.click(); }}
                      className="text-xs text-amber-400 hover:text-amber-300 underline mt-1"
                    >
                      Try again
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="flex items-center gap-2 mt-1 px-3 py-1.5 rounded-md text-xs font-medium transition-colors
                      bg-amber-500/15 border border-amber-500/30 text-amber-300 hover:bg-amber-500/25 hover:text-amber-200"
                  >
                    <Upload className="w-3.5 h-3.5" />
                    Upload Invoice PDF
                  </button>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Variance Analysis */}
        <div>
          <div className="bg-slate-700/50 rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
              <Text className="text-xs text-gray-400">Variance %</Text>
              <TrendingUp
                className={`w-4 h-4 ${
                  validation.variance_pct !== undefined
                    ? Math.abs(validation.variance_pct) < 5
                      ? "text-green-400"
                      : Math.abs(validation.variance_pct) < 15
                      ? "text-yellow-400"
                      : "text-red-400"
                    : "text-gray-400"
                }`}
              />
            </div>
            <div className="text-lg font-semibold text-white">
              {validation.variance_pct !== undefined
                ? `${validation.variance_pct > 0 ? "+" : ""}${validation.variance_pct.toFixed(1)}%`
                : "—"}
            </div>
            {validation.variance_pct !== undefined && (
              <>
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
              </>
            )}
          </div>
        </div>

        {/* Tariff Adjustment */}
        <div>
          <div className="bg-slate-700/50 rounded-lg p-3">
            <Text className="text-xs text-gray-400">Tariff Adjustment</Text>
            <div className="text-lg font-semibold text-white mt-1">
              {validation.tariff_adjustment_factor !== undefined ? (
                <>
                  {validation.tariff_adjustment_factor > 1 ? "+" : ""}
                  {((validation.tariff_adjustment_factor - 1) * 100).toFixed(1)}%
                </>
              ) : (
                "—"
              )}
            </div>
            {validation.confidence !== undefined && (
              <>
                <ProgressBar
                  value={(validation.confidence ?? 0) * 100}
                  color="blue"
                  className="mt-2"
                />
                <Text className="text-xs text-gray-500 mt-1">
                  Confidence: {((validation.confidence ?? 0) * 100).toFixed(0)}%
                </Text>
              </>
            )}
          </div>
        </div>
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
