/**
 * OptimizationPage - Full-page Load Shedding Optimization View
 *
 * Features:
 * - Full-width OptimizationPanel with all columns expanded
 * - Detailed metrics and cost analysis
 * - Scenario comparison table
 * - Action history log
 * - Execute optimization button with confirmation
 *
 * Follows SENTINEL dark theme design.
 */

import { useState, useEffect } from "react";
import {
  Zap,
  Play,
  TrendingDown,
  Thermometer,
  DollarSign,
  BarChart,
  Clock,
  CheckCircle,
  Building2,
  ChevronDown,
} from "lucide-react";
import { Table, TableHead, TableRow, TableHeaderCell, TableBody, TableCell, Button } from "@tremor/react";
import api from "../lib/api";
import type { OptimizationScenario, OptimizationStatusResponse, Site } from "../lib/api";
import { OptimizationPanel } from "../components/OptimizationPanel";
import { PageLoading } from "../components/PageLoading";

// Sentinel-styled Badge component
interface SentinelBadgeProps {
  children: React.ReactNode;
  variant?: "success" | "warning" | "error" | "info" | "neutral";
  size?: "sm" | "md" | "lg";
  className?: string;
}

function SentinelBadge({ children, variant = "neutral", size = "md", className = "" }: SentinelBadgeProps) {
  const variantStyles = {
    success: {
      bg: "rgba(16, 185, 129, 0.15)",
      color: "var(--color-sentinel-green)",
      border: "rgba(16, 185, 129, 0.3)",
    },
    warning: {
      bg: "rgba(245, 158, 11, 0.15)",
      color: "var(--color-sentinel-amber)",
      border: "rgba(245, 158, 11, 0.3)",
    },
    error: {
      bg: "rgba(220, 38, 38, 0.15)",
      color: "var(--color-sentinel-red)",
      border: "rgba(220, 38, 38, 0.3)",
    },
    info: {
      bg: "rgba(59, 130, 246, 0.15)",
      color: "var(--color-sentinel-blue)",
      border: "rgba(59, 130, 246, 0.3)",
    },
    neutral: {
      bg: "rgba(142, 142, 142, 0.15)",
      color: "var(--color-sentinel-text-secondary)",
      border: "rgba(142, 142, 142, 0.3)",
    },
  };

  const sizeStyles = {
    sm: "text-xs px-2 py-0.5",
    md: "text-sm px-2.5 py-0.5",
    lg: "text-sm px-3 py-1",
  };

  const style = variantStyles[variant];
  const sizeStyle = sizeStyles[size];

  return (
    <span
      className={`inline-flex items-center justify-center rounded font-medium whitespace-nowrap ${sizeStyle} ${className}`}
      style={{
        background: style.bg,
        color: style.color,
        border: `1px solid ${style.border}`,
      }}
    >
      {children}
    </span>
  );
}

interface ActionHistoryItem {
  timestamp: string;
  action: string;
  status: "completed" | "pending" | "failed";
  user: string;
}

interface ScenarioComparison {
  id: string;
  name: string;
  runwayExtension: string;
  energySavings: string;
  costSavings: number;
  successRate: string;
}

interface OptimizationPageProps {
  onError?: (error: string) => void;
}

export function OptimizationPage({ onError }: OptimizationPageProps) {
  // State
  const [sites, setSites] = useState<Site[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string>("site-002");
  const [allScenarios, setAllScenarios] = useState<OptimizationScenario[]>([]);
  const [scenarios, setScenarios] = useState<ScenarioComparison[]>([]);
  const [actionHistory, setActionHistory] = useState<ActionHistoryItem[]>([]);
  const [kpis, setKpis] = useState<{ energySavings: number; comfortExtension: number; fuelSavings: number; costSavings: number }>({
    energySavings: 0, comfortExtension: 0, fuelSavings: 0, costSavings: 0,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Confirmation modal
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [selectedScenario, setSelectedScenario] = useState<string | null>(null);

  // Fetch sites on mount
  useEffect(() => {
    api.getSites().then((sitesData) => {
      setSites(sitesData);
      const defaultSite = sitesData.find(s => s.id === "site-002") || sitesData[0];
      if (defaultSite) setSelectedSiteId(defaultSite.id);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    const loadOptimizationData = async () => {
      try {
        setLoading(true);

        // Fetch scenarios and optimization status in parallel
        const [scenarioData, statusData] = await Promise.all([
          api.getOptimizationScenarios().catch(() => [] as OptimizationScenario[]),
          api.getOptimizationStatus(selectedSiteId).catch(() => null as OptimizationStatusResponse | null),
        ]);

        setAllScenarios(scenarioData);

        // Build scenario comparison rows from real data
        // Add a "baseline" row (no pre-cooling) plus each scenario
        const comparisonRows: ScenarioComparison[] = [];

        if (scenarioData.length > 0) {
          // Baseline = without precooling from the first scenario
          const first = scenarioData[0];
          comparisonRows.push({
            id: "baseline",
            name: "Without Pre-cooling",
            runwayExtension: `${first.thermal_runway.without_precooling} min`,
            energySavings: "0%",
            costSavings: 0,
            successRate: "N/A",
          });

          for (const s of scenarioData) {
            comparisonRows.push({
              id: s.scenario_id,
              name: s.site_name,
              runwayExtension: `${s.thermal_runway.with_precooling} min`,
              energySavings: `${s.savings.energy_savings_percent}%`,
              costSavings: s.savings.total_savings_zar,
              successRate: s.thermal_runway.comfort_maintained ? "Yes" : "No",
            });
          }
        }
        setScenarios(comparisonRows);

        // Compute aggregate KPIs from all scenarios
        if (scenarioData.length > 0) {
          const avgEnergy = Math.round(scenarioData.reduce((sum, s) => sum + s.savings.energy_savings_percent, 0) / scenarioData.length);
          const avgComfort = Math.round(scenarioData.reduce((sum, s) => sum + s.savings.comfort_extension_minutes, 0) / scenarioData.length);
          const avgFuel = Math.round(scenarioData.reduce((sum, s) => sum + s.savings.fuel_savings_percent, 0) / scenarioData.length);
          const avgCost = Math.round(scenarioData.reduce((sum, s) => sum + s.savings.total_savings_zar, 0) / scenarioData.length);
          setKpis({ energySavings: avgEnergy, comfortExtension: avgComfort, fuelSavings: avgFuel, costSavings: avgCost });
        }

        // Build action history from optimization status
        if (statusData?.optimization_history && statusData.optimization_history.length > 0) {
          const historyItems: ActionHistoryItem[] = statusData.optimization_history
            .slice(-10)
            .reverse()
            .map((entry) => ({
              timestamp: new Date(entry.timestamp).toLocaleString(),
              action: entry.action,
              status: entry.result === "success" ? "completed" as const
                : entry.result === "error" ? "failed" as const
                : "pending" as const,
              user: entry.user || "System",
            }));
          setActionHistory(historyItems);
        } else {
          // No history yet - show empty
          setActionHistory([]);
        }

        setError(null);
      } catch (err) {
        console.error("Failed to load optimization data:", err);
        const errorMsg = "Failed to load optimization data";
        setError(errorMsg);
        onError?.(errorMsg);
      } finally {
        setLoading(false);
      }
    };

    loadOptimizationData();
  }, [selectedSiteId]);

  const handleExecuteOptimization = (scenarioId: string) => {
    setSelectedScenario(scenarioId);
    setShowConfirmModal(true);
  };

  const confirmExecution = async () => {
    setShowConfirmModal(false);

    // Find the matching scenario's site_id for precooling
    const matchedScenario = allScenarios.find((s) => s.scenario_id === selectedScenario);
    const targetSiteId = matchedScenario?.site_id || selectedSiteId;

    try {
      const result = await api.startPrecooling(targetSiteId, selectedScenario || undefined);
      const newAction: ActionHistoryItem = {
        timestamp: new Date().toLocaleString(),
        action: `Execute: ${matchedScenario?.site_name || selectedScenario} — ${result.message}`,
        status: result.success ? "completed" : "failed",
        user: "Operator",
      };
      setActionHistory([newAction, ...actionHistory]);
    } catch (_err) {
      const newAction: ActionHistoryItem = {
        timestamp: new Date().toLocaleString(),
        action: `Execute: ${matchedScenario?.site_name || selectedScenario} — Failed`,
        status: "failed",
        user: "Operator",
      };
      setActionHistory([newAction, ...actionHistory]);
    }
  };

  if (loading) {
    return (
      <PageLoading message="Loading optimization data..." />
    );
  }

  if (error) {
    return (
      <div className="h-full overflow-y-auto p-4 md:p-6" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
        <div
          className="glass-panel p-8 text-center"
        >
          <div
            className="h-12 w-12 mx-auto mb-4 rounded-full flex items-center justify-center"
            style={{ background: "rgba(239, 68, 68, 0.15)" }}
          >
            <div
              className="h-6 w-6 rounded-full"
              style={{ background: "var(--color-sentinel-red)" }}
            />
          </div>
          <h2 className="text-xl font-medium mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Error Loading Optimization Data
          </h2>
          <p style={{ color: "var(--color-sentinel-text-secondary)" }}>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-4 md:p-6" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
      {/* Main Optimization Panel - Hero Section */}
      <div className="mb-6">
        <div
          className="glass-panel overflow-hidden"
        >
          {/* Panel Header */}
          <div
            className="p-4 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--glass-border)" }}
          >
            <div className="flex items-center gap-3">
              <div
                className="p-2 rounded"
                style={{ background: "rgba(59, 130, 246, 0.15)" }}
              >
                <Zap className="h-5 w-5" style={{ color: "var(--color-sentinel-blue)" }} />
              </div>
              <div>
                <h3
                  className="font-medium text-sm"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  Load Shedding Optimization
                </h3>
                <span
                  className="text-xs"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Optimize building comfort and energy use during outages
                </span>
              </div>
            </div>
            <div className="flex items-center gap-3">
              {/* Building Selector */}
              <div className="relative">
                <Building2
                  className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                />
                <ChevronDown
                  className="absolute right-2 top-1/2 transform -translate-y-1/2 h-3 w-3 pointer-events-none"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                />
                <select
                  value={selectedSiteId}
                  onChange={(e) => setSelectedSiteId(e.target.value)}
                  className="pl-9 pr-7 py-1.5 text-sm rounded appearance-none cursor-pointer"
                  style={{
                    background: "var(--color-sentinel-bg-secondary)",
                    border: "1px solid var(--color-sentinel-border)",
                    color: "var(--color-sentinel-text-primary)",
                    outline: "none",
                    minWidth: "200px",
                  }}
                >
                  {sites.length > 0 ? (
                    sites.map((site) => (
                      <option key={site.id} value={site.id}>
                        {site.name}
                      </option>
                    ))
                  ) : (
                    <option value="site-002">Sandton City Office Tower</option>
                  )}
                </select>
              </div>

              <SentinelBadge variant="success" size="lg">
                <div className="flex items-center gap-2">
                  <div
                    className="h-2 w-2 rounded-full"
                    style={{ background: "var(--color-sentinel-green)", animation: "pulse 2s infinite" }}
                  />
                  <span>Active Monitoring</span>
                </div>
              </SentinelBadge>
            </div>
          </div>

          {/* Panel Content - Three Column Layout */}
          <div className="p-4">
            <OptimizationPanel compact={false} />
          </div>
        </div>
      </div>

      {/* Metrics Grid - KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div
          className="glass-card p-4"
        >
          <div className="flex items-center justify-between">
            <div>
              <div
                className="text-xs mb-1"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Energy Savings
              </div>
              <div
                className="text-2xl font-semibold"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                {kpis.energySavings}%
              </div>
              <div
                className="text-sm"
                style={{ color: "var(--color-sentinel-green)" }}
              >
                avg. across sites
              </div>
            </div>
            <div
              className="h-10 w-10 rounded flex items-center justify-center"
              style={{ background: "rgba(16, 185, 129, 0.15)" }}
            >
              <TrendingDown className="h-5 w-5" style={{ color: "var(--color-sentinel-green)" }} />
            </div>
          </div>
        </div>

        <div
          className="glass-card p-4"
        >
          <div className="flex items-center justify-between">
            <div>
              <div
                className="text-xs mb-1"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Comfort Extension
              </div>
              <div
                className="text-2xl font-semibold"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                {kpis.comfortExtension} min
              </div>
              <div
                className="text-sm"
                style={{ color: "var(--color-sentinel-green)" }}
              >
                avg. extension
              </div>
            </div>
            <div
              className="h-10 w-10 rounded flex items-center justify-center"
              style={{ background: "rgba(59, 130, 246, 0.15)" }}
            >
              <Thermometer className="h-5 w-5" style={{ color: "var(--color-sentinel-blue)" }} />
            </div>
          </div>
        </div>

        <div
          className="glass-card p-4"
        >
          <div className="flex items-center justify-between">
            <div>
              <div
                className="text-xs mb-1"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Fuel Savings
              </div>
              <div
                className="text-2xl font-semibold"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                {kpis.fuelSavings}%
              </div>
              <div
                className="text-sm"
                style={{ color: "var(--color-sentinel-green)" }}
              >
                avg. fuel savings
              </div>
            </div>
            <div
              className="h-10 w-10 rounded flex items-center justify-center"
              style={{ background: "rgba(245, 158, 11, 0.15)" }}
            >
              <Zap className="h-5 w-5" style={{ color: "var(--color-sentinel-amber)" }} />
            </div>
          </div>
        </div>

        <div
          className="glass-card p-4"
        >
          <div className="flex items-center justify-between">
            <div>
              <div
                className="text-xs mb-1"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Cost Savings
              </div>
              <div
                className="text-2xl font-semibold"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                {formatZAR(kpis.costSavings)}
              </div>
              <div
                className="text-sm"
                style={{ color: "var(--color-sentinel-green)" }}
              >
                avg. per outage
              </div>
            </div>
            <div
              className="h-10 w-10 rounded flex items-center justify-center"
              style={{ background: "rgba(16, 185, 129, 0.15)" }}
            >
              <DollarSign className="h-5 w-5" style={{ color: "var(--color-sentinel-green)" }} />
            </div>
          </div>
        </div>
      </div>

      {/* Scenario Comparison and Action History */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Scenario Comparison */}
        <div
          className="glass-panel overflow-hidden"
        >
          {/* Panel Header */}
          <div
            className="p-4 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--glass-border)" }}
          >
            <div className="flex items-center gap-3">
              <div
                className="p-2 rounded"
                style={{ background: "rgba(245, 158, 11, 0.15)" }}
              >
                <BarChart className="h-5 w-5" style={{ color: "var(--color-sentinel-amber)" }} />
              </div>
              <div>
                <h3
                  className="font-medium text-sm"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  Scenario Comparison
                </h3>
                <span
                  className="text-xs"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Compare optimization strategies
                </span>
              </div>
            </div>
          </div>

          {/* Panel Content */}
          <div className="p-4">
            <Table>
              <TableHead>
                <TableRow>
                  <TableHeaderCell>Scenario</TableHeaderCell>
                  <TableHeaderCell>Runway</TableHeaderCell>
                  <TableHeaderCell>Energy Savings</TableHeaderCell>
                  <TableHeaderCell>Cost</TableHeaderCell>
                  <TableHeaderCell>Success Rate</TableHeaderCell>
                  <TableHeaderCell>Action</TableHeaderCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {scenarios.map((scenario) => (
                  <TableRow key={scenario.id}>
                    <TableCell>
                      <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                        {scenario.name}
                      </span>
                    </TableCell>
                    <TableCell>
                      <SentinelBadge
                        variant={scenario.id === "baseline" ? "error" : "success"}
                        size="sm"
                      >
                        {scenario.runwayExtension}
                      </SentinelBadge>
                    </TableCell>
                    <TableCell>
                      <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                        {scenario.energySavings}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                        {formatZAR(scenario.costSavings)}
                      </span>
                    </TableCell>
                    <TableCell>
                      <SentinelBadge
                        variant={
                          scenario.id === "baseline"
                            ? "error"
                            : scenario.id === "sentinel"
                            ? "success"
                            : "warning"
                        }
                        size="sm"
                      >
                        {scenario.successRate}
                      </SentinelBadge>
                    </TableCell>
                    <TableCell>
                      {scenario.id !== "baseline" && (
                        <Button
                          size="xs"
                          onClick={() => handleExecuteOptimization(scenario.id)}
                          disabled={showConfirmModal}
                          style={{
                            background: "var(--color-sentinel-blue)",
                          }}
                        >
                          <Play className="h-3 w-3 mr-1" />
                          Execute
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>

        {/* Action History */}
        <div
          className="glass-panel overflow-hidden"
        >
          {/* Panel Header */}
          <div
            className="p-4 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--glass-border)" }}
          >
            <div className="flex items-center gap-3">
              <div
                className="p-2 rounded"
                style={{ background: "rgba(16, 185, 129, 0.15)" }}
              >
                <Clock className="h-5 w-5" style={{ color: "var(--color-sentinel-green)" }} />
              </div>
              <div>
                <h3
                  className="font-medium text-sm"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  Recent Actions
                </h3>
                <span
                  className="text-xs"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Optimization execution history
                </span>
              </div>
            </div>
          </div>

          {/* Panel Content */}
          <div className="p-4">
            <div className="space-y-3">
              {actionHistory.length === 0 && (
                <div className="p-4 rounded text-center" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                  <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    No optimization actions yet
                  </span>
                </div>
              )}
              {actionHistory.map((item, idx) => (
                <div
                  key={idx}
                  className="p-3 rounded"
                  style={{ background: "var(--color-sentinel-bg-secondary)" }}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-grow">
                      <span className="text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                        {item.action}
                      </span>
                      <div className="flex items-center gap-3 mt-1">
                        <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                          <Clock className="h-3 w-3 inline mr-1" />
                          {item.timestamp}
                        </span>
                        <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                          {item.user}
                        </span>
                      </div>
                    </div>
                    <SentinelBadge
                      size="sm"
                      variant={
                        item.status === "completed"
                          ? "success"
                          : item.status === "pending"
                          ? "warning"
                          : "error"
                      }
                    >
                      {item.status}
                    </SentinelBadge>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Confirmation Modal */}
      {showConfirmModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0"
            style={{ background: "rgba(0, 0, 0, 0.5)" }}
            onClick={() => setShowConfirmModal(false)}
          />
          <div
            className="relative z-10 glass-panel p-6"
          >
            <div className="mb-4">
              <span
                className="text-lg font-medium"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Execute Optimization
              </span>
              <span
                className="mt-2 block"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Are you sure you want to execute the {scenarios.find(s => s.id === selectedScenario)?.name} scenario?
                This will automatically adjust building controls during the load shedding event.
              </span>
            </div>
            <div className="flex justify-end gap-3">
              <Button
                size="sm"
                onClick={() => setShowConfirmModal(false)}
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  color: "var(--color-sentinel-text-primary)",
                }}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={confirmExecution}
                style={{ background: "var(--color-sentinel-green)", color: "white" }}
              >
                <CheckCircle className="h-4 w-4 mr-1" />
                Confirm
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Helper function to format ZAR currency
function formatZAR(amount: number): string {
  return new Intl.NumberFormat("en-ZA", {
    style: "currency",
    currency: "ZAR",
    minimumFractionDigits: 0,
  }).format(amount);
}

export default OptimizationPage;
