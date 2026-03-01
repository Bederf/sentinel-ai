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
} from "lucide-react";
import { useSimulation } from "@/contexts/SimulationContext";
import { useModules } from "@/contexts/ModuleHooks";
import { Table, TableHead, TableRow, TableHeaderCell, TableBody, TableCell, Button, TabGroup, TabList, Tab, TabPanels, TabPanel, Title, Text } from "@tremor/react";
import api from '@/lib/api';
import type { OptimizationScenario, OptimizationStatusResponse, Site, Prediction } from '@/lib/api';
import { fetchEnergyComparisonSummary, calculateCarbonOffset } from '@/lib/api/energy';
import type { ComparisonSummary } from '@/lib/api/energy';
import { SentinelValueCard } from '../components/SentinelValueCard';
import { OptimizationPanelGated } from "../components/OptimizationPanelGated";
import { PageLoading } from "../components/PageLoading";
import { ProfileSettings } from "../components/optimization/ProfileSettings";
import { RecommendationsDashboard } from "../components/optimization/RecommendationsDashboard";
import { RecommendationHistory } from "../components/optimization/RecommendationHistory";
import { PowerMeterValidationCard, CostValidationCard } from "../components/validation";
import { EnergyComparisonPanel } from "../components/EnergyComparisonPanel";
import { ActualVsSentinelEnergyCard } from "../components/ActualVsSentinelEnergyCard";
import { ROISummaryCard } from "../components/ROISummaryCard";

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
  // Get simulation context for live HVAC metrics
  const { running: isSimulationRunning, hvacLoadPercent, ambientTemp, simulatedHour, daysSimulated } = useSimulation();
  const { isModuleActive } = useModules();

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
  const [comparison, setComparison] = useState<ComparisonSummary | null>(null);
  const [predictions, setPredictions] = useState<Prediction[]>([]);

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

  // Fetch energy comparison for value card
  useEffect(() => {
    fetchEnergyComparisonSummary(selectedSiteId)
      .then(setComparison)
      .catch(() => {});
  }, [selectedSiteId]);

  // Fetch predictions for ROI card
  useEffect(() => {
    api.getPredictions(selectedSiteId)
      .then((data) => setPredictions(data.predictions || []))
      .catch(() => setPredictions([]));
  }, [selectedSiteId]);

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
      <TabGroup>
        <TabList className="mb-6">
          <Tab>Load Shedding</Tab>
          <Tab>Profile-Based Optimization</Tab>
          <Tab>Validation Metrics</Tab>
        </TabList>

        <TabPanels>
          <TabPanel>
      {/* Energy Value Card */}
      <div className="mb-6">
        {comparison ? (
          <SentinelValueCard
            title="Energy Optimization Impact"
            icon={Zap}
            baseline={{
              label: "Without SENTINEL",
              value: Math.round(comparison.actual.total_kwh),
              unit: "kWh",
              costZar: Math.round(comparison.actual.total_cost_zar),
            }}
            sentinel={{
              label: "With SENTINEL AI",
              value: Math.round(comparison.sentinel.total_kwh),
              unit: "kWh",
              costZar: Math.round(comparison.sentinel.total_cost_zar),
            }}
            savingsPercent={comparison.daily_savings_percent}
            carbonSavedKg={calculateCarbonOffset(comparison.actual.total_kwh - comparison.sentinel.total_kwh)}
            period="Monthly"
          />
        ) : (
          <SentinelValueCard
            title="Energy Optimization Impact"
            icon={Zap}
            baseline={{ label: "", value: 0, unit: "kWh" }}
            sentinel={{ label: "", value: 0, unit: "kWh" }}
            savingsPercent={0}
            period="Monthly"
            collecting
          />
        )}
      </div>

      {/* Load Shedding Optimization */}
      <div className="glass-card overflow-hidden mb-6">
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
                {isSimulationRunning
                  ? `Live HVAC ${hvacLoadPercent?.toFixed(0)}% load • Hour ${simulatedHour}:00 (Day ${daysSimulated}/365) • ${ambientTemp?.toFixed(1)}°C`
                  : 'Optimize building comfort and energy use during outages'
                }
              </span>
            </div>
          </div>
          <SentinelBadge variant={isSimulationRunning ? "info" : "success"} size="sm">
            {isSimulationRunning ? "Live" : "Monitoring"}
          </SentinelBadge>
        </div>
        <div className="p-4">
          <OptimizationPanelGated compact={false} />
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
                {isSimulationRunning ? "Live HVAC Load" : "Energy Savings"}
              </div>
              <div
                className="text-2xl font-semibold"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                {isSimulationRunning ? `${hvacLoadPercent?.toFixed(0)}%` : `${kpis.energySavings}%`}
              </div>
              <div
                className="text-sm"
                style={{ color: isSimulationRunning ? "var(--color-sentinel-blue)" : "var(--color-sentinel-green)" }}
              >
                {isSimulationRunning ? "Current load" : "avg. across sites"}
              </div>
            </div>
            <div
              className="h-10 w-10 rounded flex items-center justify-center"
              style={{ background: isSimulationRunning ? "rgba(59, 130, 246, 0.15)" : "rgba(16, 185, 129, 0.15)" }}
            >
              {isSimulationRunning ? (
                <Zap className="h-5 w-5" style={{ color: "var(--color-sentinel-blue)" }} />
              ) : (
                <TrendingDown className="h-5 w-5" style={{ color: "var(--color-sentinel-green)" }} />
              )}
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
                {isSimulationRunning ? "Ambient Temperature" : "Comfort Extension"}
              </div>
              <div
                className="text-2xl font-semibold"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                {isSimulationRunning ? `${ambientTemp?.toFixed(1)}°C` : `${kpis.comfortExtension} min`}
              </div>
              <div
                className="text-sm"
                style={{ color: isSimulationRunning ? "var(--color-sentinel-amber)" : "var(--color-sentinel-green)" }}
              >
                {isSimulationRunning ? "Current temp" : "avg. extension"}
              </div>
            </div>
            <div
              className="h-10 w-10 rounded flex items-center justify-center"
              style={{ background: isSimulationRunning ? "rgba(245, 158, 11, 0.15)" : "rgba(59, 130, 246, 0.15)" }}
            >
              {isSimulationRunning ? (
                <Thermometer className="h-5 w-5" style={{ color: "var(--color-sentinel-amber)" }} />
              ) : (
                <Thermometer className="h-5 w-5" style={{ color: "var(--color-sentinel-blue)" }} />
              )}
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

      {/* Scenario Comparison (Fleet ML) and Action History */}
      <div className={`grid grid-cols-1 ${isModuleActive('fleet_ml') ? 'lg:grid-cols-2' : ''} gap-6 pb-6`}>
        {/* Scenario Comparison — cross-building comparison, requires Fleet ML */}
        {isModuleActive('fleet_ml') && (
        <div
          className="glass-card overflow-hidden"
        >
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
                  Compare optimization strategies across sites
                </span>
              </div>
            </div>
          </div>

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
        )}

        {/* Action History */}
        <div
          className="glass-card overflow-hidden"
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
          </TabPanel>

          <TabPanel>
            <div className="space-y-6">
              <ProfileSettings
                siteId={selectedSiteId}
                onProfileChange={() => {}}
              />
              <RecommendationsDashboard siteId={selectedSiteId} />
              <RecommendationHistory siteId={selectedSiteId} />
            </div>
          </TabPanel>

          <TabPanel>
            <div className="space-y-6">
              {/* Energy Impact Comparison */}
              <EnergyComparisonPanel siteId={selectedSiteId} />

              {/* Actual vs SENTINEL Energy */}
              <div className="glass-panel rounded-md overflow-hidden">
                <ActualVsSentinelEnergyCard siteId={selectedSiteId} />
              </div>

              {/* Validation Metrics */}
              <div>
                <Title className="mb-4">Energy &amp; Cost Validation</Title>
                <Text className="text-gray-400 mb-4">
                  Real-time validation of simulated energy consumption and costs against meter readings and invoices.
                </Text>
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <PowerMeterValidationCard buildingId={selectedSiteId} />
                <CostValidationCard buildingId={selectedSiteId} />
              </div>

              {/* ROI Summary */}
              {predictions.length > 0 && (
                <ROISummaryCard predictions={predictions} />
              )}
            </div>
          </TabPanel>
        </TabPanels>
      </TabGroup>
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
