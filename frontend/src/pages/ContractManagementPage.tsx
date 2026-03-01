/**
 * ContractManagementPage - Contract & SLA Management Dashboard
 *
 * Four sections:
 * 1. Portfolio Overview - KPI cards (total contracts, revenue, margin)
 * 2. Contract List - Sortable table with status filtering
 * 3. SLA Tracking - SLA term cards with traffic-light indicators
 * 4. Budget Overview - Budget vs actual breakdown with variance
 *
 * Falls back to demo data when API is unavailable.
 * Follows SENTINEL dark theme design patterns.
 */

import { useState, useEffect, useCallback, useMemo } from "react";
import {
  FileText,
  DollarSign,
  TrendingUp,
  AlertTriangle,
  CheckCircle,
  Clock,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Shield,
  Target,
  Users,
  Building2,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import {
  Table,
  TableHead,
  TableRow,
  TableHeaderCell,
  TableBody,
  TableCell,
  Select,
  SelectItem,
} from "@tremor/react";
import type { Contract, BudgetVariance, BudgetAlert } from "../lib/contractApi";
import type { SLAPerformanceRecord } from "../lib/profitabilityApi";
import { PageLoading } from "../components/PageLoading";

// ============= Demo Data =============

const DEMO_CONTRACT: Contract = {
  id: "demo-contract-001",
  contract_code: "CON-DEMO-2024",
  organization: {
    code: "ORG-DEMO",
    name: "Demo Operations",
    tier: "enterprise",
    primary_contact_name: "Site Operations",
    primary_contact_email: "ops@demo.local",
    primary_contact_phone: "+27 11 555 0102",
  },
  contract: {
    type: "full_maintenance",
    status: "active",
    start_date: "2024-01-01",
    end_date: "2026-12-31",
    auto_renew: true,
    monthly_fee_zar: 285000,
    pricing_basis: "fixed_monthly",
    payment_terms: "30 days net",
    billing_cycle_days: 30,
  },
  sla_terms: [
    {
      metric_type: "uptime_percent",
      target_value: 99.0,
      measurement_period_days: 30,
      penalty_per_breach_zar: 5000,
      penalty_cap_monthly_zar: 25000,
      exclusions: ["scheduled_maintenance", "force_majeure", "client_caused"],
      current_value: 99.4,
      status: "met",
    },
    {
      metric_type: "response_time_hours",
      target_value: 4,
      measurement_period_days: 30,
      penalty_per_breach_zar: 2500,
      penalty_cap_monthly_zar: 15000,
      exclusions: ["after_hours_weekends"],
      current_value: 3.2,
      status: "met",
    },
    {
      metric_type: "resolution_time_hours",
      target_value: 24,
      measurement_period_days: 30,
      penalty_per_breach_zar: 3500,
      penalty_cap_monthly_zar: 20000,
      exclusions: ["parts_on_order", "specialist_required"],
      current_value: 21.5,
      status: "at_risk",
    },
  ],
  budget: {
    year: 2026,
    monthly_total_zar: 245000,
    breakdown: {
      labor_zar: 120000,
      parts_zar: 65000,
      subcontractors_zar: 35000,
      overhead_zar: 25000,
    },
    risk_buffer_percent: 12,
    equipment_type_budgets: {
      CHILLER: 45000,
      AHU: 30000,
      FCU: 15000,
      GEN: 35000,
      UPS: 20000,
      DALI: 10000,
      other: 90000,
    },
  },
  condition_assessment: {
    date: "2023-12-15",
    assessor: "Johan Pretorius",
    overall_score: 3.8,
    mechanical_score: 3.5,
    electrical_score: 4.0,
    structural_score: 4.2,
    notes:
      "Building in good condition overall. Chillers showing age (8 years), recommend proactive bearing replacement program.",
    risk_factors: [
      "chiller_age",
      "cooling_tower_condition",
      "generator_battery_age",
    ],
  },
  profitability_snapshot: {
    ytd_revenue_zar: 285000,
    ytd_direct_costs_zar: 218000,
    ytd_overhead_zar: 25000,
    ytd_penalties_zar: 2500,
    gross_margin_percent: 23.5,
    net_margin_percent: 13.9,
  },
};

const DEMO_BUDGET_VARIANCE: BudgetVariance[] = [
  {
    category: "Labor",
    budgeted_zar: 120000,
    actual_zar: 115000,
    variance_zar: -5000,
    variance_percent: -4.2,
  },
  {
    category: "Parts",
    budgeted_zar: 65000,
    actual_zar: 72000,
    variance_zar: 7000,
    variance_percent: 10.8,
  },
  {
    category: "Subcontractors",
    budgeted_zar: 35000,
    actual_zar: 31000,
    variance_zar: -4000,
    variance_percent: -11.4,
  },
  {
    category: "Overhead",
    budgeted_zar: 25000,
    actual_zar: 25000,
    variance_zar: 0,
    variance_percent: 0,
  },
];

// ============= Utility Components =============

interface SentinelBadgeProps {
  children: React.ReactNode;
  variant?: "success" | "warning" | "error" | "info" | "neutral";
  size?: "sm" | "md";
  className?: string;
}

function SentinelBadge({
  children,
  variant = "neutral",
  size = "md",
  className = "",
}: SentinelBadgeProps) {
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

function formatZAR(amount: number): string {
  return new Intl.NumberFormat("en-ZA", {
    style: "currency",
    currency: "ZAR",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

function formatMetricType(type: string): string {
  const labels: Record<string, string> = {
    uptime_percent: "System Uptime",
    response_time_hours: "Response Time",
    resolution_time_hours: "Resolution Time",
    ppm_completion_percent: "PPM Completion",
  };
  return labels[type] || type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatMetricValue(type: string, value: number): string {
  if (type.includes("percent")) return `${value.toFixed(1)}%`;
  if (type.includes("hours")) return `${value.toFixed(1)}h`;
  return value.toString();
}

function getSlaStatusVariant(
  status?: string
): "success" | "warning" | "error" {
  if (status === "met") return "success";
  if (status === "at_risk") return "warning";
  if (status === "breached") return "error";
  return "success";
}

function getContractStatusVariant(
  status: string
): "success" | "warning" | "error" | "neutral" {
  if (status === "active") return "success";
  if (status === "expiring_soon") return "warning";
  if (status === "expired" || status === "terminated") return "error";
  return "neutral";
}

// ============= KPI Card =============

interface KPICardProps {
  title: string;
  value: string;
  subtitle?: string;
  icon: React.ReactNode;
  trend?: { value: string; positive: boolean };
}

function KPICard({ title, value, subtitle, icon, trend }: KPICardProps) {
  return (
    <div
      className="glass-card p-4 rounded-lg overflow-hidden"
      style={{
        border: "1px solid var(--color-sentinel-border)",
        background: "rgba(14, 116, 144, 0.05)",
      }}
    >
      <div className="flex items-start justify-between mb-3">
        <span
          className="text-xs font-medium uppercase tracking-wider"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          {title}
        </span>
        <div
          className="p-2 rounded"
          style={{ background: "rgba(59, 130, 246, 0.15)" }}
        >
          {icon}
        </div>
      </div>
      <div
        className="text-2xl font-bold"
        style={{ color: "var(--color-sentinel-text-primary)" }}
      >
        {value}
      </div>
      <div className="flex items-center gap-2 mt-1">
        {subtitle && (
          <span
            className="text-xs"
            style={{ color: "var(--color-sentinel-text-disabled)" }}
          >
            {subtitle}
          </span>
        )}
        {trend && (
          <span
            className="text-xs font-medium flex items-center gap-1"
            style={{
              color: trend.positive
                ? "var(--color-sentinel-green)"
                : "var(--color-sentinel-red)",
            }}
          >
            {trend.positive ? (
              <TrendingUp className="h-3 w-3" />
            ) : (
              <ChevronDown className="h-3 w-3" />
            )}
            {trend.value}
          </span>
        )}
      </div>
    </div>
  );
}

// ============= Budget Bar =============

interface BudgetBarProps {
  category: string;
  budgeted: number;
  actual: number;
  variancePercent: number;
}

function BudgetBar({
  category,
  budgeted,
  actual,
  variancePercent,
}: BudgetBarProps) {
  const maxVal = Math.max(budgeted, actual);
  const budgetWidth = maxVal > 0 ? (budgeted / maxVal) * 100 : 0;
  const actualWidth = maxVal > 0 ? (actual / maxVal) * 100 : 0;
  const isOver = actual > budgeted;

  return (
    <div className="mb-4">
      <div className="flex items-center justify-between mb-1.5">
        <span
          className="text-sm font-medium"
          style={{ color: "var(--color-sentinel-text-primary)" }}
        >
          {category}
        </span>
        <span
          className="text-xs font-medium"
          style={{
            color: isOver
              ? "var(--color-sentinel-red)"
              : "var(--color-sentinel-green)",
          }}
        >
          {variancePercent > 0 ? "+" : ""}
          {variancePercent.toFixed(1)}%
        </span>
      </div>
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <span
            className="text-xs w-16 flex-shrink-0"
            style={{ color: "var(--color-sentinel-text-disabled)" }}
          >
            Budget
          </span>
          <div className="flex-1 h-4 rounded overflow-hidden" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
            <div
              className="h-full rounded"
              style={{
                width: `${budgetWidth}%`,
                background: "rgba(59, 130, 246, 0.5)",
              }}
            />
          </div>
          <span
            className="text-xs w-20 text-right flex-shrink-0"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            {formatZAR(budgeted)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="text-xs w-16 flex-shrink-0"
            style={{ color: "var(--color-sentinel-text-disabled)" }}
          >
            Actual
          </span>
          <div className="flex-1 h-4 rounded overflow-hidden" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
            <div
              className="h-full rounded"
              style={{
                width: `${actualWidth}%`,
                background: isOver
                  ? "rgba(220, 38, 38, 0.6)"
                  : "rgba(16, 185, 129, 0.6)",
              }}
            />
          </div>
          <span
            className="text-xs w-20 text-right flex-shrink-0"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            {formatZAR(actual)}
          </span>
        </div>
      </div>
    </div>
  );
}

// ============= Main Page Component =============

export function ContractManagementPage() {
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [selectedContract, setSelectedContract] = useState<Contract | null>(null);
  const [budgetVariance, setBudgetVariance] = useState<BudgetVariance[]>([]);
  const [budgetReport, setBudgetReport] = useState<{
    equipment_type_breakdown: {
      equipment_type: string;
      total_budget_zar: number;
      total_actual_zar: number;
      variance_zar: number;
      spend_percentage: number;
    }[];
    alert_summary?: {
      warning?: number;
      critical?: number;
      open?: number;
      resolved?: number;
    };
  } | null>(null);
  const [budgetAlerts, setBudgetAlerts] = useState<BudgetAlert[]>([]);
  const [slaPerformance, setSlaPerformance] = useState<SLAPerformanceRecord[]>([]);
  const [alertSeverityFilter, setAlertSeverityFilter] = useState<string>("all");
  const [alertStatusFilter, setAlertStatusFilter] = useState<string>("all");
  const [showAllAlerts, setShowAllAlerts] = useState(false);
  const [alertPage, setAlertPage] = useState(1);
  const alertsPerPage = 5;
  const [renewalPricing, setRenewalPricing] = useState<{
    current_monthly_fee_zar: number;
    actual_cost_monthly_avg_zar: number;
    target_margin_pct: number;
    recommended_monthly_fee_zar: number;
    delta_zar: number;
    delta_pct: number;
    notes: string[];
  } | null>(null);
  const [benchmarks, setBenchmarks] = useState<{
    similar_contracts: number;
    average_monthly_fee_zar: number;
    min_monthly_fee_zar: number;
    max_monthly_fee_zar: number;
  } | null>(null);
  const [pricingLoading, setPricingLoading] = useState(false);
  const [pricingError, setPricingError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [buildingFilter, setBuildingFilter] = useState<string | null>(null);
  const [sortField, setSortField] = useState<string>("client");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");

  // Load contracts on mount
  useEffect(() => {
    const loadContracts = async () => {
      setLoading(true);
      try {
        // Try API first
        const { contractApi } = await import("../lib/contractApi");
        const data = await contractApi.getContracts();
        if (data && data.length > 0) {
          setContracts(data);
        } else {
          // Fall back to demo data
          setContracts([DEMO_CONTRACT]);
        }
      } catch {
        // API not available - use demo data
        setContracts([DEMO_CONTRACT]);
      } finally {
        setLoading(false);
      }
    };
    loadContracts();
  }, []);

  // Load budget variance when contract selected
  useEffect(() => {
    if (!selectedContract) {
      setBudgetVariance([]);
      setBudgetReport(null);
      setBudgetAlerts([]);
      setRenewalPricing(null);
      setBenchmarks(null);
      setPricingError(null);
      setSlaPerformance([]);
      return;
    }

    const loadVariance = async () => {
      try {
        const { contractApi } = await import("../lib/contractApi");
        const contractId = selectedContract.id || selectedContract.contract_code;
        const reportData = await contractApi.getBudgetReport(
          contractId,
          selectedContract.budget.year
        );
        const varianceData = await contractApi.getBudgetVariance(
          contractId,
          selectedContract.budget.year
        );
        const alertData = await contractApi.getBudgetAlerts(
          contractId,
          selectedContract.budget.year
        );

        setBudgetReport(reportData || null);
        setBudgetVariance(varianceData || []);
        setBudgetAlerts(alertData || []);
      } catch {
        setBudgetVariance(DEMO_BUDGET_VARIANCE);
        setBudgetReport(null);
        setBudgetAlerts([]);
      }
    };
    loadVariance();
  }, [selectedContract]);

  useEffect(() => {
    if (!selectedContract) return;
    const contractId = selectedContract.id;
    if (!contractId || contractId.startsWith("demo")) {
      setSlaPerformance([]);
      return;
    }

    const loadSlaPerformance = async () => {
      try {
        const { profitabilityApi } = await import("../lib/profitabilityApi");
        const response = await profitabilityApi.getSLAPerformance(
          contractId,
          12
        );
        setSlaPerformance(response.performance || []);
      } catch (err) {
        console.error("Failed to load SLA performance:", err);
        setSlaPerformance([]);
      }
    };

    loadSlaPerformance();
  }, [selectedContract]);

  const handleBudgetExport = async (format: "csv" | "pdf") => {
    if (!selectedContract) return;
    const contractId = selectedContract.id || selectedContract.contract_code;
    try {
      const { contractApi } = await import("../lib/contractApi");
      const blob = await contractApi.exportBudgetReport(
        contractId,
        selectedContract.budget.year,
        format
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `budget-report-${contractId}-${selectedContract.budget.year}.${format}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Budget export failed:", err);
    }
  };

  useEffect(() => {
    if (!selectedContract) {
      return;
    }

    const buildDemoRenewalPricing = () => {
      const currentFee = selectedContract.contract.monthly_fee_zar;
      const actualCost = currentFee * 0.72;
      const targetMargin = 25;
      const recommended = actualCost * (1 + targetMargin / 100);
      return {
        current_monthly_fee_zar: currentFee,
        actual_cost_monthly_avg_zar: Math.round(actualCost),
        target_margin_pct: targetMargin,
        recommended_monthly_fee_zar: Math.round(recommended),
        delta_zar: Math.round(recommended - currentFee),
        delta_pct: currentFee > 0 ? Math.round(((recommended - currentFee) / currentFee) * 1000) / 10 : 0,
        notes: ["Demo estimate (no live cost data)."],
      };
    };

    const buildDemoBenchmarks = () => {
      const fees = contracts.map((c) => c.contract.monthly_fee_zar);
      const avg =
        fees.length > 0 ? fees.reduce((sum, f) => sum + f, 0) / fees.length : 0;
      return {
        similar_contracts: Math.max(1, fees.length),
        average_monthly_fee_zar: Math.round(avg),
        min_monthly_fee_zar: Math.round(Math.min(...fees, selectedContract.contract.monthly_fee_zar)),
        max_monthly_fee_zar: Math.round(Math.max(...fees, selectedContract.contract.monthly_fee_zar)),
      };
    };

    const loadPricing = async () => {
      const contractId = selectedContract.id;
      if (!contractId || contractId.startsWith("demo")) {
        setRenewalPricing(buildDemoRenewalPricing());
        setBenchmarks(buildDemoBenchmarks());
        return;
      }

      setPricingLoading(true);
      setPricingError(null);
      try {
        const { pricingApi } = await import("../lib/pricingApi");
        const [renewal, benchmark] = await Promise.all([
          pricingApi.getRenewalPricing(
            contractId,
            selectedContract.budget.year,
            "standard"
          ),
          pricingApi.getBenchmarks(contractId),
        ]);
        setRenewalPricing(renewal);
        setBenchmarks(benchmark);
      } catch (err) {
        console.error("Pricing fetch failed:", err);
        setPricingError("Pricing data unavailable");
        setRenewalPricing(buildDemoRenewalPricing());
        setBenchmarks(buildDemoBenchmarks());
      } finally {
        setPricingLoading(false);
      }
    };

    loadPricing();
  }, [selectedContract, contracts]);

  // Extract unique buildings for dropdown
  const buildings = useMemo(() => {
    const buildingSet = new Set<string>();
    contracts.forEach((c) => {
      // Extract building from organization name or use a default
      const building = c.organization.name || "Unknown";
      buildingSet.add(building);
    });
    return Array.from(buildingSet).sort();
  }, [contracts]);

  // Compute portfolio KPIs
  const totalContracts = contracts.length;
  const activeContracts = contracts.filter(
    (c) => c.contract.status === "active"
  ).length;
  const monthlyRevenue = contracts.reduce(
    (sum, c) => sum + c.contract.monthly_fee_zar,
    0
  );
  const avgMargin =
    contracts.length > 0
      ? contracts.reduce(
          (sum, c) => sum + (c.profitability_snapshot?.gross_margin_percent || 0),
          0
        ) / contracts.length
      : 0;

  // Filter and sort contracts
  const filteredContracts = contracts.filter((c) => {
    // Filter by building
    if (buildingFilter && c.organization.name !== buildingFilter) {
      return false;
    }
    // Filter by status
    if (statusFilter === "all") return true;
    return c.contract.status === statusFilter;
  });

  const handleSort = useCallback(
    (field: string) => {
      if (sortField === field) {
        setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
      } else {
        setSortField(field);
        setSortDirection("asc");
      }
    },
    [sortField]
  );

  const sortedContracts = [...filteredContracts].sort((a, b) => {
    const dir = sortDirection === "asc" ? 1 : -1;
    switch (sortField) {
      case "client":
        return dir * a.organization.name.localeCompare(b.organization.name);
      case "type":
        return dir * a.contract.type.localeCompare(b.contract.type);
      case "status":
        return dir * a.contract.status.localeCompare(b.contract.status);
      case "fee":
        return dir * (a.contract.monthly_fee_zar - b.contract.monthly_fee_zar);
      case "margin":
        return (
          dir *
          ((a.profitability_snapshot?.gross_margin_percent || 0) -
            (b.profitability_snapshot?.gross_margin_percent || 0))
        );
      default:
        return 0;
    }
  });

  const handleContractClick = (contract: Contract) => {
    setSelectedContract(
      selectedContract?.contract_code === contract.contract_code
        ? null
        : contract
    );
  };

  const SortIcon = ({
    field,
  }: {
    field: string;
  }) => {
    if (sortField !== field) return null;
    return sortDirection === "asc" ? (
      <ChevronUp className="h-3 w-3 inline ml-1" />
    ) : (
      <ChevronDown className="h-3 w-3 inline ml-1" />
    );
  };

  // Loading skeleton
  if (loading) {
    return (
      <PageLoading message="Loading contract portfolio..." />
    );
  }

  return (
    <div
      className="h-full overflow-y-auto p-4 md:p-6"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Section 1: Portfolio Overview */}
        <div>
          <div className="flex items-center gap-3 mb-4">
            <div
              className="p-2 rounded"
              style={{ background: "rgba(245, 158, 11, 0.15)" }}
            >
              <FileText
                className="h-5 w-5"
                style={{ color: "var(--color-sentinel-amber)" }}
              />
            </div>
            <h2
              className="text-lg font-semibold"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Portfolio Overview
            </h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <KPICard
              title="Total Contracts"
              value={totalContracts.toString()}
              subtitle={`${activeContracts} active`}
              icon={
                <FileText
                  className="h-4 w-4"
                  style={{ color: "var(--color-sentinel-blue)" }}
                />
              }
            />
            <KPICard
              title="Active Contracts"
              value={activeContracts.toString()}
              subtitle="Currently serviced"
              icon={
                <CheckCircle
                  className="h-4 w-4"
                  style={{ color: "var(--color-sentinel-green)" }}
                />
              }
            />
            <KPICard
              title="Monthly Revenue"
              value={formatZAR(monthlyRevenue)}
              subtitle="All contracts"
              icon={
                <DollarSign
                  className="h-4 w-4"
                  style={{ color: "var(--color-sentinel-amber)" }}
                />
              }
              trend={{ value: "+2.5%", positive: true }}
            />
            <KPICard
              title="Average Margin"
              value={`${avgMargin.toFixed(1)}%`}
              subtitle="Gross margin"
              icon={
                <TrendingUp
                  className="h-4 w-4"
                  style={{ color: "var(--color-sentinel-green)" }}
                />
              }
              trend={{ value: "+1.2%", positive: true }}
            />
          </div>
        </div>

        {/* Contract Status Summary */}
        <div className="flex items-center gap-3 flex-wrap">
          <span
            className="text-xs font-medium uppercase tracking-wider"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            Status:
          </span>
          <div className="flex items-center gap-1.5">
            <div
              className="w-2 h-2 rounded-full"
              style={{ background: "var(--color-sentinel-green)" }}
            />
            <span
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              {activeContracts} Active
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <div
              className="w-2 h-2 rounded-full"
              style={{ background: "var(--color-sentinel-amber)" }}
            />
            <span
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              {
                contracts.filter((c) => c.contract.status === "expiring_soon")
                  .length
              }{" "}
              Expiring Soon
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <div
              className="w-2 h-2 rounded-full"
              style={{ background: "var(--color-sentinel-red)" }}
            />
            <span
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              {
                contracts.filter(
                  (c) =>
                    c.contract.status === "expired" ||
                    c.contract.status === "terminated"
                ).length
              }{" "}
              Expired/Terminated
            </span>
          </div>
        </div>

        {/* Section 2: Contract List */}
        <div
          className="glass-panel overflow-hidden"
        >
          <div
            className="px-4 py-3 flex items-center justify-between"
            style={{
              borderBottom: "1px solid var(--color-sentinel-border)",
            }}
          >
            <div className="flex items-center gap-3">
              <div
                className="p-2 rounded"
                style={{ background: "rgba(59, 130, 246, 0.15)" }}
              >
                <FileText
                  className="h-4 w-4"
                  style={{ color: "var(--color-sentinel-blue)" }}
                />
              </div>
              <h3
                className="text-sm font-medium"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Contract Portfolio
              </h3>
            </div>
            {/* Building filter + Status filter */}
            <div className="flex items-center gap-3">
              {/* Building selector */}
              <Select
                value={buildingFilter || "all"}
                onValueChange={(v) =>
                  setBuildingFilter(v === "all" ? null : v)
                }
                className="w-48"
              >
                <SelectItem value="all">All Buildings</SelectItem>
                {buildings.map((building) => (
                  <SelectItem key={building} value={building}>
                    {building}
                  </SelectItem>
                ))}
              </Select>

              {/* Status filter buttons */}
              <div className="flex items-center gap-2">
                {["all", "active", "draft", "expired"].map((status) => (
                  <button
                    key={status}
                    onClick={() => setStatusFilter(status)}
                    className="text-xs px-3 py-1 rounded transition-colors"
                    style={{
                      background:
                        statusFilter === status
                          ? "var(--color-sentinel-bg-secondary)"
                          : "transparent",
                      color:
                        statusFilter === status
                          ? "var(--color-sentinel-text-primary)"
                          : "var(--color-sentinel-text-disabled)",
                      border:
                        statusFilter === status
                          ? "1px solid var(--color-sentinel-border)"
                          : "1px solid transparent",
                    }}
                  >
                    {status.charAt(0).toUpperCase() + status.slice(1)}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="overflow-x-auto">
            <Table>
              <TableHead>
                <TableRow
                  style={{
                    background: "var(--color-sentinel-bg-secondary)",
                  }}
                >
                  <TableHeaderCell
                    className="cursor-pointer select-none"
                    onClick={() => handleSort("client")}
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    Client
                    <SortIcon field="client" />
                  </TableHeaderCell>
                  <TableHeaderCell
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    Building
                  </TableHeaderCell>
                  <TableHeaderCell
                    className="cursor-pointer select-none"
                    onClick={() => handleSort("type")}
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    Type
                    <SortIcon field="type" />
                  </TableHeaderCell>
                  <TableHeaderCell
                    className="cursor-pointer select-none"
                    onClick={() => handleSort("status")}
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    Status
                    <SortIcon field="status" />
                  </TableHeaderCell>
                  <TableHeaderCell
                    className="cursor-pointer select-none text-right"
                    onClick={() => handleSort("fee")}
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    Monthly Fee
                    <SortIcon field="fee" />
                  </TableHeaderCell>
                  <TableHeaderCell
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    SLA Score
                  </TableHeaderCell>
                  <TableHeaderCell
                    className="cursor-pointer select-none text-right"
                    onClick={() => handleSort("margin")}
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    Margin %
                    <SortIcon field="margin" />
                  </TableHeaderCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {sortedContracts.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7}>
                      <div
                        className="text-center py-8"
                        style={{
                          color: "var(--color-sentinel-text-disabled)",
                        }}
                      >
                        No contracts found
                      </div>
                    </TableCell>
                  </TableRow>
                ) : (
                  sortedContracts.map((contract) => {
                    const isSelected =
                      selectedContract?.contract_code ===
                      contract.contract_code;
                    const slasMet = contract.sla_terms.filter(
                      (s) => s.status === "met" || !s.status
                    ).length;
                    const totalSlas = contract.sla_terms.length;
                    const slaScore =
                      totalSlas > 0
                        ? Math.round((slasMet / totalSlas) * 100)
                        : 100;

                    return (
                      <TableRow
                        key={contract.contract_code}
                        className="cursor-pointer transition-colors"
                        onClick={() => handleContractClick(contract)}
                        style={{
                          background: isSelected
                            ? "rgba(245, 158, 11, 0.08)"
                            : "transparent",
                          borderLeft: isSelected
                            ? "3px solid var(--color-sentinel-amber)"
                            : "3px solid transparent",
                        }}
                      >
                        <TableCell>
                          <div>
                            <div
                              className="text-sm font-medium"
                              style={{
                                color:
                                  "var(--color-sentinel-text-primary)",
                              }}
                            >
                              {contract.organization.name}
                            </div>
                            <div
                              className="text-xs"
                              style={{
                                color:
                                  "var(--color-sentinel-text-disabled)",
                              }}
                            >
                              {contract.contract_code}
                            </div>
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-1.5">
                            <Building2
                              className="h-3.5 w-3.5"
                              style={{
                                color:
                                  "var(--color-sentinel-text-disabled)",
                              }}
                            />
                            <span
                              className="text-sm"
                              style={{
                                color:
                                  "var(--color-sentinel-text-secondary)",
                              }}
                            >
                              Sandton City
                            </span>
                          </div>
                        </TableCell>
                        <TableCell>
                          <span
                            className="text-sm capitalize"
                            style={{
                              color:
                                "var(--color-sentinel-text-secondary)",
                            }}
                          >
                            {contract.contract.type.replace(/_/g, " ")}
                          </span>
                        </TableCell>
                        <TableCell>
                          <SentinelBadge
                            variant={getContractStatusVariant(
                              contract.contract.status
                            )}
                            size="sm"
                          >
                            {contract.contract.status
                              .replace(/_/g, " ")
                              .replace(/\b\w/g, (c) => c.toUpperCase())}
                          </SentinelBadge>
                        </TableCell>
                        <TableCell className="text-right">
                          <span
                            className="text-sm font-medium"
                            style={{
                              color:
                                "var(--color-sentinel-text-primary)",
                            }}
                          >
                            {formatZAR(contract.contract.monthly_fee_zar)}
                          </span>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <div
                              className="flex-1 h-2 rounded-full max-w-[60px]"
                              style={{
                                background:
                                  "var(--color-sentinel-bg-secondary)",
                              }}
                            >
                              <div
                                className="h-full rounded-full"
                                style={{
                                  width: `${slaScore}%`,
                                  background:
                                    slaScore >= 80
                                      ? "var(--color-sentinel-green)"
                                      : slaScore >= 60
                                        ? "var(--color-sentinel-amber)"
                                        : "var(--color-sentinel-red)",
                                }}
                              />
                            </div>
                            <span
                              className="text-xs font-medium"
                              style={{
                                color:
                                  slaScore >= 80
                                    ? "var(--color-sentinel-green)"
                                    : slaScore >= 60
                                      ? "var(--color-sentinel-amber)"
                                      : "var(--color-sentinel-red)",
                              }}
                            >
                              {slasMet}/{totalSlas}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell className="text-right">
                          <span
                            className="text-sm font-medium"
                            style={{
                              color:
                                (contract.profitability_snapshot
                                  ?.gross_margin_percent || 0) >= 15
                                  ? "var(--color-sentinel-green)"
                                  : (contract.profitability_snapshot
                                        ?.gross_margin_percent || 0) >= 10
                                    ? "var(--color-sentinel-amber)"
                                    : "var(--color-sentinel-red)",
                            }}
                          >
                            {(
                              contract.profitability_snapshot
                                ?.gross_margin_percent || 0
                            ).toFixed(1)}
                            %
                          </span>
                        </TableCell>
                      </TableRow>
                    );
                  })
                )}
              </TableBody>
            </Table>
          </div>
        </div>

        {/* Section 3 & 4: Detail Panels (shown when contract selected) */}
        {selectedContract && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Section 3: SLA Tracking */}
            <div
              className="glass-panel overflow-hidden"
            >
              <div
                className="px-4 py-3 flex items-center gap-3"
                style={{
                  borderBottom: "1px solid var(--color-sentinel-border)",
                }}
              >
                <div
                  className="p-2 rounded"
                  style={{ background: "rgba(245, 158, 11, 0.15)" }}
                >
                  <Shield
                    className="h-4 w-4"
                    style={{ color: "var(--color-sentinel-amber)" }}
                  />
                </div>
                <h3
                  className="text-sm font-medium"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  SLA Tracking
                </h3>
                <span
                  className="text-xs ml-auto"
                  style={{ color: "var(--color-sentinel-text-disabled)" }}
                >
                  {selectedContract.contract_code}
                </span>
              </div>

              <div className="p-4 space-y-3">
                {selectedContract.sla_terms.map((term, idx) => {
                  const status = term.status || "met";
                  const variant = getSlaStatusVariant(status);
                  const currentVal = term.current_value ?? term.target_value;
                  const isLowerBetter = term.metric_type.includes("time");
                  const progressPercent = isLowerBetter
                    ? Math.max(
                        0,
                        Math.min(
                          100,
                          ((term.target_value - currentVal) /
                            term.target_value) *
                            100 +
                            100
                        )
                      )
                    : Math.max(
                        0,
                        Math.min(
                          100,
                          (currentVal / term.target_value) * 100
                        )
                      );

                  return (
                    <div
                      key={idx}
                      className="rounded-lg p-3"
                      style={{
                        background: "var(--color-sentinel-bg-secondary)",
                        border: "1px solid var(--color-sentinel-border)",
                      }}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <Target
                            className="h-4 w-4"
                            style={{
                              color:
                                variant === "success"
                                  ? "var(--color-sentinel-green)"
                                  : variant === "warning"
                                    ? "var(--color-sentinel-amber)"
                                    : "var(--color-sentinel-red)",
                            }}
                          />
                          <span
                            className="text-sm font-medium"
                            style={{
                              color: "var(--color-sentinel-text-primary)",
                            }}
                          >
                            {formatMetricType(term.metric_type)}
                          </span>
                        </div>
                        <SentinelBadge variant={variant} size="sm">
                          {status === "met"
                            ? "Met"
                            : status === "at_risk"
                              ? "At Risk"
                              : "Breached"}
                        </SentinelBadge>
                      </div>

                      <div className="flex items-center justify-between mb-2">
                        <span
                          className="text-xs"
                          style={{
                            color: "var(--color-sentinel-text-disabled)",
                          }}
                        >
                          Target: {formatMetricValue(term.metric_type, term.target_value)}
                        </span>
                        <span
                          className="text-sm font-bold"
                          style={{
                            color: "var(--color-sentinel-text-primary)",
                          }}
                        >
                          {formatMetricValue(term.metric_type, currentVal)}
                        </span>
                      </div>

                      {/* Progress bar */}
                      <div
                        className="h-2 rounded-full overflow-hidden"
                        style={{
                          background: "var(--color-sentinel-bg-primary)",
                        }}
                      >
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{
                            width: `${Math.min(100, progressPercent)}%`,
                            background:
                              variant === "success"
                                ? "var(--color-sentinel-green)"
                                : variant === "warning"
                                  ? "var(--color-sentinel-amber)"
                                  : "var(--color-sentinel-red)",
                          }}
                        />
                      </div>

                      {/* Penalty exposure */}
                      <div className="flex items-center justify-between mt-2">
                        <span
                          className="text-xs"
                          style={{
                            color: "var(--color-sentinel-text-disabled)",
                          }}
                        >
                          Penalty/breach: {formatZAR(term.penalty_per_breach_zar)}
                        </span>
                        <span
                          className="text-xs"
                          style={{
                            color: "var(--color-sentinel-text-disabled)",
                          }}
                        >
                          Cap: {formatZAR(term.penalty_cap_monthly_zar)}/mo
                        </span>
                      </div>
                    </div>
                  );
                })}

                {/* Penalty exposure summary */}
                <div
                  className="rounded-lg p-3 mt-2"
                  style={{
                    background: "rgba(220, 38, 38, 0.08)",
                    border: "1px solid rgba(220, 38, 38, 0.2)",
                  }}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <AlertTriangle
                      className="h-4 w-4"
                      style={{ color: "var(--color-sentinel-amber)" }}
                    />
                    <span
                      className="text-xs font-medium"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      Penalty Exposure Summary
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span
                      className="text-xs"
                      style={{
                        color: "var(--color-sentinel-text-secondary)",
                      }}
                    >
                      Max monthly exposure
                    </span>
                    <span
                      className="text-sm font-bold"
                      style={{ color: "var(--color-sentinel-red)" }}
                    >
                      {formatZAR(
                        selectedContract.sla_terms.reduce(
                          (sum, t) => sum + t.penalty_cap_monthly_zar,
                          0
                        )
                      )}
                    </span>
                  </div>
                  <div className="flex items-center justify-between mt-1">
                    <span
                      className="text-xs"
                      style={{
                        color: "var(--color-sentinel-text-secondary)",
                      }}
                    >
                      YTD penalties incurred
                    </span>
                    <span
                      className="text-sm font-bold"
                      style={{ color: "var(--color-sentinel-amber)" }}
                    >
                      {formatZAR(
                        selectedContract.profitability_snapshot
                          ?.ytd_penalties_zar || 0
                      )}
                    </span>
                  </div>
                </div>

                {/* SLA Penalty Trend */}
                <div className="mt-4">
                  <h4
                    className="text-xs font-medium uppercase tracking-wider mb-2"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    SLA Penalty Trend
                  </h4>
                  {slaPerformance.length === 0 ? (
                    <div
                      className="text-xs"
                      style={{ color: "var(--color-sentinel-text-disabled)" }}
                    >
                      No penalty data available
                    </div>
                  ) : (
                    <div className="h-[180px] w-full">
                      {(() => {
                        const penaltyCap = selectedContract.sla_terms.reduce(
                          (sum, term) => sum + (term.penalty_cap_monthly_zar || 0),
                          0
                        );
                        const chartData = slaPerformance.map((row) => ({
                          period:
                            row.period_start?.toString().slice(0, 7) ||
                            row.period_end?.toString().slice(0, 7) ||
                            "N/A",
                          clawback: row.clawback_amount_zar || 0,
                          cap: penaltyCap,
                        }));
                        return (
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chartData}>
                          <CartesianGrid
                            strokeDasharray="3 3"
                            stroke="var(--color-sentinel-border)"
                          />
                          <XAxis
                            dataKey="period"
                            stroke="var(--color-sentinel-text-secondary)"
                            fontSize={11}
                          />
                          <YAxis
                            stroke="var(--color-sentinel-text-secondary)"
                            fontSize={11}
                            tickFormatter={(value) => `R${value}`}
                          />
                          <Tooltip
                            contentStyle={{
                              background: "var(--color-sentinel-bg-panel)",
                              border: "1px solid var(--color-sentinel-border)",
                              borderRadius: "4px",
                            }}
                            labelStyle={{ color: "var(--color-sentinel-text-primary)" }}
                            formatter={(value: number) => [`R${value.toFixed(0)}`, "Penalty"]}
                          />
                          <Line
                            type="monotone"
                            dataKey="clawback"
                            stroke="var(--color-sentinel-amber)"
                            strokeWidth={2}
                            dot={{ fill: "var(--color-sentinel-amber)", r: 3 }}
                            activeDot={{ r: 5 }}
                          />
                          <Line
                            type="monotone"
                            dataKey="cap"
                            stroke="var(--color-sentinel-red)"
                            strokeWidth={1.5}
                            strokeDasharray="4 4"
                            dot={false}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                        );
                      })()}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Section 4: Budget Overview */}
            <div
              className="glass-panel overflow-hidden"
            >
              <div
                className="px-4 py-3 flex items-center gap-3"
                style={{
                  borderBottom: "1px solid var(--color-sentinel-border)",
                }}
              >
                <div
                  className="p-2 rounded"
                  style={{ background: "rgba(34, 197, 94, 0.15)" }}
                >
                  <DollarSign
                    className="h-4 w-4"
                    style={{ color: "var(--color-sentinel-green)" }}
                  />
                </div>
                <h3
                  className="text-sm font-medium"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  Budget Overview
                </h3>
                <div className="ml-auto flex items-center gap-2">
                  <button
                    className="text-xs px-2 py-1 rounded"
                    style={{
                      color: "var(--color-sentinel-text-primary)",
                      border: "1px solid var(--color-sentinel-border)",
                    }}
                    onClick={() => handleBudgetExport("csv")}
                  >
                    Export CSV
                  </button>
                  <button
                    className="text-xs px-2 py-1 rounded"
                    style={{
                      color: "var(--color-sentinel-text-primary)",
                      border: "1px solid var(--color-sentinel-border)",
                    }}
                    onClick={() => handleBudgetExport("pdf")}
                  >
                    Export PDF
                  </button>
                </div>
                <span
                  className="text-xs"
                  style={{ color: "var(--color-sentinel-text-disabled)" }}
                >
                  FY {selectedContract.budget.year}
                </span>
              </div>

              <div className="p-4">
                {/* Budget summary KPIs */}
                <div className="grid grid-cols-3 gap-3 mb-5">
                  <div className="text-center">
                    <div
                      className="text-xs"
                      style={{
                        color: "var(--color-sentinel-text-disabled)",
                      }}
                    >
                      Monthly Budget
                    </div>
                    <div
                      className="text-sm font-bold mt-0.5"
                      style={{
                        color: "var(--color-sentinel-text-primary)",
                      }}
                    >
                      {formatZAR(selectedContract.budget.monthly_total_zar)}
                    </div>
                  </div>
                  <div className="text-center">
                    <div
                      className="text-xs"
                      style={{
                        color: "var(--color-sentinel-text-disabled)",
                      }}
                    >
                      Monthly Fee
                    </div>
                    <div
                      className="text-sm font-bold mt-0.5"
                      style={{ color: "var(--color-sentinel-green)" }}
                    >
                      {formatZAR(selectedContract.contract.monthly_fee_zar)}
                    </div>
                  </div>
                  <div className="text-center">
                    <div
                      className="text-xs"
                      style={{
                        color: "var(--color-sentinel-text-disabled)",
                      }}
                    >
                      Risk Buffer
                    </div>
                    <div
                      className="text-sm font-bold mt-0.5"
                      style={{ color: "var(--color-sentinel-amber)" }}
                    >
                      {selectedContract.budget.risk_buffer_percent}%
                    </div>
                  </div>
                </div>

                {/* Budget vs Actual bars */}
                <div className="mb-4">
                  <h4
                    className="text-xs font-medium uppercase tracking-wider mb-3"
                    style={{
                      color: "var(--color-sentinel-text-secondary)",
                    }}
                  >
                    Budget vs Actual
                  </h4>
                  {budgetReport?.equipment_type_breakdown?.length ? (
                    <div className="flex flex-wrap gap-2 mb-3">
                      {budgetReport.equipment_type_breakdown.map((row) => {
                        const variant =
                          row.spend_percentage >= 100
                            ? "error"
                            : row.spend_percentage >= 80
                              ? "warning"
                              : "success";
                        return (
                          <SentinelBadge
                            key={row.equipment_type}
                            variant={variant}
                            size="sm"
                          >
                            {row.equipment_type} {row.spend_percentage.toFixed(0)}%
                          </SentinelBadge>
                        );
                      })}
                    </div>
                  ) : null}
                  {budgetReport?.alert_summary && (
                    <div className="flex flex-wrap gap-2 mb-3">
                      <SentinelBadge variant="warning" size="sm">
                        Warnings {budgetReport.alert_summary.warning || 0}
                      </SentinelBadge>
                      <SentinelBadge variant="error" size="sm">
                        Critical {budgetReport.alert_summary.critical || 0}
                      </SentinelBadge>
                      <SentinelBadge variant="info" size="sm">
                        Open {budgetReport.alert_summary.open || 0}
                      </SentinelBadge>
                      <SentinelBadge variant="neutral" size="sm">
                        Resolved {budgetReport.alert_summary.resolved || 0}
                      </SentinelBadge>
                    </div>
                  )}
                  {budgetVariance.map((item) => (
                    <BudgetBar
                      key={item.category}
                      category={item.category}
                      budgeted={item.budgeted_zar}
                      actual={item.actual_zar}
                      variancePercent={item.variance_percent}
                    />
                  ))}
                </div>

                {budgetReport?.equipment_type_breakdown?.length ? (
                  <div className="mb-4">
                    <h4
                      className="text-xs font-medium uppercase tracking-wider mb-3"
                      style={{
                        color: "var(--color-sentinel-text-secondary)",
                      }}
                    >
                      Equipment Type Budget
                    </h4>
                    {budgetReport.equipment_type_breakdown.map((row) => (
                      <BudgetBar
                        key={row.equipment_type}
                        category={row.equipment_type}
                        budgeted={row.total_budget_zar}
                        actual={row.total_actual_zar}
                        variancePercent={row.spend_percentage}
                      />
                    ))}
                  </div>
                ) : null}

                {budgetAlerts.length > 0 && (
                  <div
                    className="rounded-lg p-3 mb-4"
                    style={{
                      background: "rgba(245, 158, 11, 0.08)",
                      border: "1px solid rgba(245, 158, 11, 0.2)",
                    }}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <AlertTriangle
                        className="h-4 w-4"
                        style={{ color: "var(--color-sentinel-amber)" }}
                      />
                      <span
                        className="text-xs font-medium"
                        style={{ color: "var(--color-sentinel-text-primary)" }}
                      >
                        Budget Alerts
                      </span>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 mb-3">
                      <select
                        className="text-xs rounded px-2 py-1"
                        style={{
                          background: "var(--color-sentinel-bg-primary)",
                          color: "var(--color-sentinel-text-primary)",
                          border: "1px solid var(--color-sentinel-border)",
                        }}
                        value={alertSeverityFilter}
                        onChange={(e) => {
                          setAlertSeverityFilter(e.target.value);
                          setAlertPage(1);
                        }}
                      >
                        <option value="all">All Severities</option>
                        <option value="warning">Warning</option>
                        <option value="critical">Critical</option>
                      </select>
                      <select
                        className="text-xs rounded px-2 py-1"
                        style={{
                          background: "var(--color-sentinel-bg-primary)",
                          color: "var(--color-sentinel-text-primary)",
                          border: "1px solid var(--color-sentinel-border)",
                        }}
                        value={alertStatusFilter}
                        onChange={(e) => {
                          setAlertStatusFilter(e.target.value);
                          setAlertPage(1);
                        }}
                      >
                        <option value="all">All Status</option>
                        <option value="open">Open</option>
                        <option value="acknowledged">Acknowledged</option>
                        <option value="resolved">Resolved</option>
                      </select>
                      <button
                        className="text-xs px-2 py-1 rounded"
                        style={{
                          border: "1px solid var(--color-sentinel-border)",
                          color: "var(--color-sentinel-text-primary)",
                        }}
                        onClick={() => {
                          setShowAllAlerts((prev) => !prev);
                          setAlertPage(1);
                        }}
                      >
                        {showAllAlerts ? "Show Top 5" : "Show All"}
                      </button>
                    </div>
                    {(() => {
                      const filteredAlerts = budgetAlerts
                        .filter((alert) =>
                          alertSeverityFilter === "all"
                            ? true
                            : alert.severity === alertSeverityFilter
                        )
                        .filter((alert) =>
                          alertStatusFilter === "all"
                            ? true
                            : alert.status === alertStatusFilter
                        );
                      const totalPages = Math.max(
                        1,
                        Math.ceil(filteredAlerts.length / alertsPerPage)
                      );
                      const pageStart = (alertPage - 1) * alertsPerPage;
                      const pageAlerts = showAllAlerts
                        ? filteredAlerts
                        : filteredAlerts.slice(pageStart, pageStart + alertsPerPage);

                      return (
                        <div className="space-y-2">
                          {pageAlerts.map((alert) => (
                        <div
                          key={alert.id || `${alert.period_month}-${alert.severity}-${alert.equipment_type || "total"}`}
                          className="flex items-center justify-between text-xs"
                          style={{ color: "var(--color-sentinel-text-secondary)" }}
                        >
                          <span>
                            {alert.equipment_type
                              ? `${alert.equipment_type} · `
                              : ""}
                            {alert.message || "Budget alert"}
                          </span>
                          <div className="flex items-center gap-2">
                            <SentinelBadge
                              variant={alert.severity === "critical" ? "error" : "warning"}
                              size="sm"
                            >
                              {alert.severity}
                            </SentinelBadge>
                            {alert.id && alert.status !== "acknowledged" && (
                              <button
                                className="text-xs"
                                style={{ color: "var(--color-sentinel-blue)" }}
                                onClick={async () => {
                                  const { contractApi } = await import("../lib/contractApi");
                                  const updated = await contractApi.updateBudgetAlertStatus(
                                    alert.id!,
                                    "acknowledged"
                                  );
                                  setBudgetAlerts((prev) =>
                                    prev.map((item) =>
                                      item.id === updated.id ? { ...item, status: updated.status } : item
                                    )
                                  );
                                }}
                              >
                                Ack
                              </button>
                            )}
                            {alert.id && alert.status !== "resolved" && (
                              <button
                                className="text-xs"
                                style={{ color: "var(--color-sentinel-green)" }}
                                onClick={async () => {
                                  const { contractApi } = await import("../lib/contractApi");
                                  const updated = await contractApi.updateBudgetAlertStatus(
                                    alert.id!,
                                    "resolved"
                                  );
                                  setBudgetAlerts((prev) =>
                                    prev.map((item) =>
                                      item.id === updated.id ? { ...item, status: updated.status } : item
                                    )
                                  );
                                }}
                              >
                                Resolve
                              </button>
                            )}
                          </div>
                        </div>
                          ))}
                          {!showAllAlerts && totalPages > 1 && (
                            <div className="flex items-center justify-end gap-2 pt-2">
                              <button
                                className="text-xs px-2 py-1 rounded"
                                style={{
                                  border: "1px solid var(--color-sentinel-border)",
                                  color: "var(--color-sentinel-text-primary)",
                                }}
                                onClick={() =>
                                  setAlertPage((page) => Math.max(1, page - 1))
                                }
                                disabled={alertPage === 1}
                              >
                                Prev
                              </button>
                              <span
                                className="text-xs"
                                style={{ color: "var(--color-sentinel-text-disabled)" }}
                              >
                                Page {alertPage} of {totalPages}
                              </span>
                              <button
                                className="text-xs px-2 py-1 rounded"
                                style={{
                                  border: "1px solid var(--color-sentinel-border)",
                                  color: "var(--color-sentinel-text-primary)",
                                }}
                                onClick={() =>
                                  setAlertPage((page) =>
                                    Math.min(totalPages, page + 1)
                                  )
                                }
                                disabled={alertPage === totalPages}
                              >
                                Next
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    })()}
                  </div>
                )}

                {/* Profitability snapshot */}
                {selectedContract.profitability_snapshot && (
                  <div
                    className="rounded-lg p-3"
                    style={{
                      background: "var(--color-sentinel-bg-secondary)",
                      border: "1px solid var(--color-sentinel-border)",
                    }}
                  >
                    <h4
                      className="text-xs font-medium uppercase tracking-wider mb-2"
                      style={{
                        color: "var(--color-sentinel-text-secondary)",
                      }}
                    >
                      Profitability
                    </h4>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <div
                          className="text-xs"
                          style={{
                            color: "var(--color-sentinel-text-disabled)",
                          }}
                        >
                          YTD Revenue
                        </div>
                        <div
                          className="text-sm font-bold"
                          style={{
                            color: "var(--color-sentinel-text-primary)",
                          }}
                        >
                          {formatZAR(
                            selectedContract.profitability_snapshot
                              .ytd_revenue_zar
                          )}
                        </div>
                      </div>
                      <div>
                        <div
                          className="text-xs"
                          style={{
                            color: "var(--color-sentinel-text-disabled)",
                          }}
                        >
                          YTD Costs
                        </div>
                        <div
                          className="text-sm font-bold"
                          style={{
                            color: "var(--color-sentinel-text-primary)",
                          }}
                        >
                          {formatZAR(
                            selectedContract.profitability_snapshot
                              .ytd_direct_costs_zar +
                              selectedContract.profitability_snapshot
                                .ytd_overhead_zar
                          )}
                        </div>
                      </div>
                      <div>
                        <div
                          className="text-xs"
                          style={{
                            color: "var(--color-sentinel-text-disabled)",
                          }}
                        >
                          Gross Margin
                        </div>
                        <div
                          className="text-sm font-bold"
                          style={{ color: "var(--color-sentinel-green)" }}
                        >
                          {selectedContract.profitability_snapshot.gross_margin_percent.toFixed(
                            1
                          )}
                          %
                        </div>
                      </div>
                      <div>
                        <div
                          className="text-xs"
                          style={{
                            color: "var(--color-sentinel-text-disabled)",
                          }}
                        >
                          Net Margin
                        </div>
                        <div
                          className="text-sm font-bold"
                          style={{
                            color:
                              selectedContract.profitability_snapshot
                                .net_margin_percent >= 10
                                ? "var(--color-sentinel-green)"
                                : "var(--color-sentinel-amber)",
                          }}
                        >
                          {selectedContract.profitability_snapshot.net_margin_percent.toFixed(
                            1
                          )}
                          %
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Renewal Pricing */}
                {renewalPricing && (
                  <div
                    className="rounded-lg p-3 mt-3"
                    style={{
                      background: "var(--color-sentinel-bg-secondary)",
                      border: "1px solid var(--color-sentinel-border)",
                    }}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <TrendingUp
                          className="h-4 w-4"
                          style={{ color: "var(--color-sentinel-blue)" }}
                        />
                        <h4
                          className="text-xs font-medium uppercase tracking-wider"
                          style={{
                            color: "var(--color-sentinel-text-secondary)",
                          }}
                        >
                          Renewal Pricing
                        </h4>
                      </div>
                      {pricingLoading && (
                        <RefreshCw
                          className="h-4 w-4 animate-spin"
                          style={{ color: "var(--color-sentinel-text-disabled)" }}
                        />
                      )}
                    </div>

                    {pricingError && (
                      <div
                        className="text-xs mb-2"
                        style={{ color: "var(--color-sentinel-red)" }}
                      >
                        {pricingError}
                      </div>
                    )}

                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <div
                          className="text-xs"
                          style={{
                            color: "var(--color-sentinel-text-disabled)",
                          }}
                        >
                          Current Fee
                        </div>
                        <div
                          className="text-sm font-bold"
                          style={{
                            color: "var(--color-sentinel-text-primary)",
                          }}
                        >
                          {formatZAR(renewalPricing.current_monthly_fee_zar)}
                        </div>
                      </div>
                      <div>
                        <div
                          className="text-xs"
                          style={{
                            color: "var(--color-sentinel-text-disabled)",
                          }}
                        >
                          Recommended Fee
                        </div>
                        <div
                          className="text-sm font-bold"
                          style={{
                            color: "var(--color-sentinel-green)",
                          }}
                        >
                          {formatZAR(renewalPricing.recommended_monthly_fee_zar)}
                        </div>
                      </div>
                      <div>
                        <div
                          className="text-xs"
                          style={{
                            color: "var(--color-sentinel-text-disabled)",
                          }}
                        >
                          Delta
                        </div>
                        <div
                          className="text-sm font-bold"
                          style={{
                            color:
                              renewalPricing.delta_zar >= 0
                                ? "var(--color-sentinel-amber)"
                                : "var(--color-sentinel-green)",
                          }}
                        >
                          {formatZAR(renewalPricing.delta_zar)} (
                          {renewalPricing.delta_pct.toFixed(1)}%)
                        </div>
                      </div>
                      <div>
                        <div
                          className="text-xs"
                          style={{
                            color: "var(--color-sentinel-text-disabled)",
                          }}
                        >
                          Target Margin
                        </div>
                        <div
                          className="text-sm font-bold"
                          style={{
                            color: "var(--color-sentinel-text-primary)",
                          }}
                        >
                          {renewalPricing.target_margin_pct.toFixed(1)}%
                        </div>
                      </div>
                    </div>

                    {benchmarks && (
                      <div
                        className="mt-3 rounded-lg p-2"
                        style={{
                          background: "rgba(14, 116, 144, 0.08)",
                          border: "1px solid rgba(14, 116, 144, 0.2)",
                        }}
                      >
                        <div
                          className="text-xs"
                          style={{ color: "var(--color-sentinel-text-secondary)" }}
                        >
                          Benchmarks ({benchmarks.similar_contracts} similar)
                        </div>
                        <div
                          className="text-xs mt-1"
                          style={{ color: "var(--color-sentinel-text-primary)" }}
                        >
                          Avg {formatZAR(benchmarks.average_monthly_fee_zar)} · Min{" "}
                          {formatZAR(benchmarks.min_monthly_fee_zar)} · Max{" "}
                          {formatZAR(benchmarks.max_monthly_fee_zar)}
                        </div>
                      </div>
                    )}

                    {renewalPricing.notes?.length > 0 && (
                      <div
                        className="text-xs mt-2"
                        style={{ color: "var(--color-sentinel-text-disabled)" }}
                      >
                        {renewalPricing.notes.join(" ")}
                      </div>
                    )}
                  </div>
                )}

                {/* Condition Assessment */}
                {selectedContract.condition_assessment && (
                  <div
                    className="rounded-lg p-3 mt-3"
                    style={{
                      background: "var(--color-sentinel-bg-secondary)",
                      border: "1px solid var(--color-sentinel-border)",
                    }}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <h4
                        className="text-xs font-medium uppercase tracking-wider"
                        style={{
                          color: "var(--color-sentinel-text-secondary)",
                        }}
                      >
                        Condition Assessment
                      </h4>
                      <span
                        className="text-xs"
                        style={{
                          color: "var(--color-sentinel-text-disabled)",
                        }}
                      >
                        {selectedContract.condition_assessment.date}
                      </span>
                    </div>
                    <div className="grid grid-cols-4 gap-2 mb-2">
                      {[
                        {
                          label: "Overall",
                          score:
                            selectedContract.condition_assessment
                              .overall_score,
                        },
                        {
                          label: "Mech",
                          score:
                            selectedContract.condition_assessment
                              .mechanical_score,
                        },
                        {
                          label: "Elec",
                          score:
                            selectedContract.condition_assessment
                              .electrical_score,
                        },
                        {
                          label: "Struct",
                          score:
                            selectedContract.condition_assessment
                              .structural_score,
                        },
                      ].map(({ label, score }) => (
                        <div key={label} className="text-center">
                          <div
                            className="text-lg font-bold"
                            style={{
                              color:
                                score >= 4
                                  ? "var(--color-sentinel-green)"
                                  : score >= 3
                                    ? "var(--color-sentinel-amber)"
                                    : "var(--color-sentinel-red)",
                            }}
                          >
                            {score.toFixed(1)}
                          </div>
                          <div
                            className="text-xs"
                            style={{
                              color:
                                "var(--color-sentinel-text-disabled)",
                            }}
                          >
                            {label}
                          </div>
                        </div>
                      ))}
                    </div>
                    {selectedContract.condition_assessment.risk_factors
                      .length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {selectedContract.condition_assessment.risk_factors.map(
                          (factor) => (
                            <span
                              key={factor}
                              className="text-xs px-2 py-0.5 rounded"
                              style={{
                                background: "rgba(220, 38, 38, 0.1)",
                                border: "1px solid rgba(220, 38, 38, 0.2)",
                                color: "var(--color-sentinel-red)",
                              }}
                            >
                              {factor.replace(/_/g, " ")}
                            </span>
                          )
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Contact details for selected contract */}
        {selectedContract && (
          <div
            className="glass-panel p-4"
          >
            <div className="flex items-center gap-2 mb-3">
              <Users
                className="h-4 w-4"
                style={{ color: "var(--color-sentinel-amber)" }}
              />
              <h3
                className="text-sm font-medium"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Client Contact
              </h3>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <div
                  className="text-xs"
                  style={{
                    color: "var(--color-sentinel-text-disabled)",
                  }}
                >
                  Contact Name
                </div>
                <div
                  className="text-sm font-medium mt-0.5"
                  style={{
                    color: "var(--color-sentinel-text-primary)",
                  }}
                >
                  {selectedContract.organization.primary_contact_name}
                </div>
              </div>
              <div>
                <div
                  className="text-xs"
                  style={{
                    color: "var(--color-sentinel-text-disabled)",
                  }}
                >
                  Email
                </div>
                <div
                  className="text-sm font-medium mt-0.5"
                  style={{
                    color: "var(--color-sentinel-blue)",
                  }}
                >
                  {selectedContract.organization.primary_contact_email}
                </div>
              </div>
              <div>
                <div
                  className="text-xs"
                  style={{
                    color: "var(--color-sentinel-text-disabled)",
                  }}
                >
                  Phone
                </div>
                <div
                  className="text-sm font-medium mt-0.5"
                  style={{
                    color: "var(--color-sentinel-text-primary)",
                  }}
                >
                  {selectedContract.organization.primary_contact_phone}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-4 mt-3">
              <div className="flex items-center gap-1.5">
                <Clock
                  className="h-3.5 w-3.5"
                  style={{
                    color: "var(--color-sentinel-text-disabled)",
                  }}
                />
                <span
                  className="text-xs"
                  style={{
                    color: "var(--color-sentinel-text-secondary)",
                  }}
                >
                  {selectedContract.contract.start_date} to{" "}
                  {selectedContract.contract.end_date}
                </span>
              </div>
              {selectedContract.contract.auto_renew && (
                <SentinelBadge variant="info" size="sm">
                  Auto-Renew
                </SentinelBadge>
              )}
              <SentinelBadge variant="neutral" size="sm">
                {selectedContract.contract.payment_terms}
              </SentinelBadge>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
