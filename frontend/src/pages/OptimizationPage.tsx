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
import { Table, TableHead, TableRow, TableHeaderCell, TableBody, TableCell, Button } from "@tremor/react";
import api from "../lib/api";
import type { EskomStatusResponse, ThermalRunwayResponse } from "../lib/api";
import { OptimizationPanel } from "../components/OptimizationPanel";

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
  const [_eskomStatus, setEskomStatus] = useState<EskomStatusResponse | null>(null);
  const [_thermalRunway, setThermalRunway] = useState<ThermalRunwayResponse | null>(null);
  const [scenarios, setScenarios] = useState<ScenarioComparison[]>([]);
  const [actionHistory, setActionHistory] = useState<ActionHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Confirmation modal
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [selectedScenario, setSelectedScenario] = useState<string | null>(null);

  useEffect(() => {
    const loadOptimizationData = async () => {
      try {
        setLoading(true);
        const [statusData, thermalData] = await Promise.all([
          api.getEskomStatus(undefined),
          api.getThermalRunway("gateway-theatre"),
        ]);
        setEskomStatus(statusData);
        setThermalRunway(thermalData);

        // Load mock scenario comparisons
        setScenarios([
          {
            id: "baseline",
            name: "Without Pre-cooling",
            runwayExtension: "52 min",
            energySavings: "0%",
            costSavings: 0,
            successRate: "68%",
          },
          {
            id: "sentinel",
            name: "SENTINEL Optimized",
            runwayExtension: "108 min",
            energySavings: "12%",
            costSavings: 1250,
            successRate: "94%",
          },
          {
            id: "aggressive",
            name: "Aggressive Pre-cooling",
            runwayExtension: "142 min",
            energySavings: "8%",
            costSavings: 980,
            successRate: "89%",
          },
        ]);

        // Load mock action history
        setActionHistory([
          {
            timestamp: "2026-01-27 14:45:00",
            action: "Initiate pre-cooling sequence",
            status: "completed",
            user: "Auto (SENTINEL)",
          },
          {
            timestamp: "2026-01-27 14:50:00",
            action: "Adjust CHW setpoint: 6°C → 5°C",
            status: "completed",
            user: "Auto (SENTINEL)",
          },
          {
            timestamp: "2026-01-27 14:55:00",
            action: "Increase AHU fan speed: 70% → 90%",
            status: "completed",
            user: "Auto (SENTINEL)",
          },
          {
            timestamp: "2026-01-27 15:00:00",
            action: "Switch to ventilation only mode",
            status: "completed",
            user: "Auto (SENTINEL)",
          },
          {
            timestamp: "2026-01-27 15:30:00",
            action: "Verify pre-cooling complete: 20.5°C achieved",
            status: "completed",
            user: "Auto (SENTINEL)",
          },
          {
            timestamp: "2026-01-27 16:00:00",
            action: "Load shedding begins - monitoring building drift",
            status: "pending",
            user: "System",
          },
        ]);

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
  }, []);

  const handleExecuteOptimization = (scenarioId: string) => {
    setSelectedScenario(scenarioId);
    setShowConfirmModal(true);
  };

  const confirmExecution = () => {
    // Simulate optimization execution
    console.log(`Executing optimization scenario: ${selectedScenario}`);
    setShowConfirmModal(false);

    // Add to action history
    const newAction: ActionHistoryItem = {
      timestamp: new Date().toLocaleString(),
      action: `Execute optimization: ${scenarios.find(s => s.id === selectedScenario)?.name}`,
      status: "completed",
      user: "Operator",
    };
    setActionHistory([newAction, ...actionHistory]);
  };

  if (loading) {
    return (
      <div className="h-full overflow-y-auto p-4 md:p-6" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2" style={{ borderColor: "var(--color-sentinel-blue)" }} />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full overflow-y-auto p-4 md:p-6" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
        <div
          className="rounded-md p-8 text-center"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
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
          className="rounded-md overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          {/* Panel Header */}
          <div
            className="p-4 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
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
            <div className="flex items-center gap-2">
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
          className="rounded-md p-4"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
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
                12%
              </div>
              <div
                className="text-sm"
                style={{ color: "var(--color-sentinel-green)" }}
              >
                ↓ R1,250 per outage
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
          className="rounded-md p-4"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
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
                56 min
              </div>
              <div
                className="text-sm"
                style={{ color: "var(--color-sentinel-green)" }}
              >
                ↓ 108% longer
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
          className="rounded-md p-4"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
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
                20%
              </div>
              <div
                className="text-sm"
                style={{ color: "var(--color-sentinel-green)" }}
              >
                ↓ R850 per outage
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
          className="rounded-md p-4"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
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
                R2,100
              </div>
              <div
                className="text-sm"
                style={{ color: "var(--color-sentinel-green)" }}
              >
                per 4hr outage
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
          className="rounded-md overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          {/* Panel Header */}
          <div
            className="p-4 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
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
          className="rounded-md overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          {/* Panel Header */}
          <div
            className="p-4 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
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
            className="relative z-10 rounded-md p-6"
            style={{
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-border)",
            }}
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
