/**
 * ProfitabilityDashboardPage - Portfolio Profitability Analytics
 *
 * Four sections:
 * 1. Portfolio Overview - KPI cards (revenue, margin, profit/loss counts)
 * 2. Loss Leaders Alert - Warning panel for loss-making contracts
 * 3. Contract Profitability Table - Sortable table with drill-down
 * 4. Trend Charts - Margin % over time with improving/stable/declining indicators
 *
 * Integrates with profitabilityApi for portfolio metrics and trends.
 */

import { useState, useEffect, useMemo } from "react";
import {
  Minus,
  AlertTriangle,
  RefreshCw,
  ArrowUp,
  ArrowDown,
  DollarSign,
} from "lucide-react";
import {
  Card,
  Title,
  Text,
  Badge,
  Callout,
  Button,
  Select,
  SelectItem,
} from "@tremor/react";
import {
  Table,
  TableHead,
  TableRow,
  TableHeaderCell,
  TableBody,
  TableCell,
} from "@tremor/react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { profitabilityApi } from "../lib/profitabilityApi";
import type {
  PortfolioMetrics,
  ContractProfitabilityDetail,
  ProfitabilityTrend,
  LossLeaderAnalysis,
  ContractProfitabilityReport,
  AssetROIListItem,
  SLAPerformanceRecord,
} from "../lib/profitabilityApi";
import { PageLoading } from "../components/PageLoading";

// ============= Period Filter =============

type PeriodOption = "this_month" | "last_month" | "last_quarter" | "ytd";

interface PeriodRange {
  start: string;
  end: string;
  label: string;
}

function getPeriodRange(option: PeriodOption): PeriodRange {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();

  switch (option) {
    case "this_month":
      return {
        start: new Date(year, month, 1).toISOString().split("T")[0],
        end: new Date(year, month + 1, 0).toISOString().split("T")[0],
        label: "This Month",
      };
    case "last_month":
      return {
        start: new Date(year, month - 1, 1).toISOString().split("T")[0],
        end: new Date(year, month, 0).toISOString().split("T")[0],
        label: "Last Month",
      };
    case "last_quarter":
      const quarterStart = Math.floor(month / 3) * 3;
      return {
        start: new Date(year, quarterStart - 3, 1).toISOString().split("T")[0],
        end: new Date(year, quarterStart, 0).toISOString().split("T")[0],
        label: "Last Quarter",
      };
    case "ytd":
      return {
        start: new Date(year, 0, 1).toISOString().split("T")[0],
        end: new Date().toISOString().split("T")[0],
        label: "YTD",
      };
  }
}

// ============= KPI Card Component =============

interface KPICardProps {
  title: string;
  value: string;
  subtitle?: string;
  trend?: "up" | "down" | "neutral";
  color?: "green" | "red" | "blue" | "gray";
}

function KPICard({ title, value, subtitle, trend, color = "blue" }: KPICardProps) {
  const colorMap = {
    green: "var(--color-sentinel-green)",
    red: "var(--color-sentinel-red)",
    blue: "var(--color-sentinel-blue)",
    gray: "var(--color-sentinel-text-secondary)",
  };

  const TrendIcon = trend === "up" ? ArrowUp : trend === "down" ? ArrowDown : Minus;

  return (
    <Card style={{ background: "rgba(14, 116, 144, 0.05)", border: "1px solid var(--color-sentinel-border)" }}>
      <div className="flex items-center justify-between">
        <div>
          <Text
            style={{ color: "var(--color-sentinel-text-secondary)" }}
            className="text-xs"
          >
            {title}
          </Text>
          <Title
            style={{ color: "var(--color-sentinel-text-primary)" }}
            className="text-2xl font-semibold mt-1"
          >
            {value}
          </Title>
          {subtitle && (
            <Text
              style={{ color: "var(--color-sentinel-text-disabled)" }}
              className="text-xs mt-1"
            >
              {subtitle}
            </Text>
          )}
        </div>
        {trend && (
          <div className="flex items-center gap-1">
            <TrendIcon
              className="h-4 w-4"
              style={{ color: colorMap[color] }}
            />
          </div>
        )}
      </div>
    </Card>
  );
}

// ============= Main Component =============

export function ProfitabilityDashboardPage() {
  // Data state
  const [portfolioMetrics, setPortfolioMetrics] =
    useState<PortfolioMetrics | null>(null);
  const [lossLeaders, setLossLeaders] = useState<LossLeaderAnalysis[]>([]);
  const [contracts, setContracts] = useState<ContractProfitabilityDetail[]>([]);
  const [trends, setTrends] = useState<ProfitabilityTrend[]>([]);
  const [slaPerformance, setSlaPerformance] = useState<SLAPerformanceRecord[]>([]);
  const [selectedReport, setSelectedReport] =
    useState<ContractProfitabilityReport | null>(null);
  const [selectedAssets, setSelectedAssets] = useState<AssetROIListItem[]>([]);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);

  // UI state
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [periodFilter, setPeriodFilter] = useState<PeriodOption>("this_month");
  const [buildingFilter, setBuildingFilter] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedContractId, setSelectedContractId] = useState<string | null>(
    null
  );

  // Table sorting
  const [sortField, setSortField] = useState<"margin" | "revenue" | "status">(
    "margin"
  );
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 10;

  // Get period range from filter
  const periodRange = useMemo(() => getPeriodRange(periodFilter), [periodFilter]);

  // Format currency as ZAR
  const formatZAR = (amount: number) => {
    return new Intl.NumberFormat("en-ZA", {
      style: "currency",
      currency: "ZAR",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  // Format percentage
  const formatPercent = (value: number) => {
    return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
  };

  const statusRank = (status: ContractProfitabilityDetail["status"]) => {
    switch (status) {
      case "profitable":
        return 2;
      case "break_even":
        return 1;
      default:
        return 0;
    }
  };

  const formatStatusLabel = (status: ContractProfitabilityDetail["status"]) => {
    if (status === "break_even") return "Break Even";
    return status.charAt(0).toUpperCase() + status.slice(1);
  };

  const aggregatePortfolioTrends = (
    allTrends: ProfitabilityTrend[][]
  ): ProfitabilityTrend[] => {
    const periodMap = new Map<
      string,
      { revenue: number; cost: number; margin: number; marginPctSum: number; count: number }
    >();

    allTrends.forEach((trendList) => {
      trendList.forEach((trend) => {
        const entry = periodMap.get(trend.period) || {
          revenue: 0,
          cost: 0,
          margin: 0,
          marginPctSum: 0,
          count: 0,
        };
        entry.revenue += trend.revenue_zar;
        entry.cost += trend.cost_zar;
        entry.margin += trend.margin_zar;
        entry.marginPctSum += trend.margin_pct;
        entry.count += 1;
        periodMap.set(trend.period, entry);
      });
    });

    const periods = Array.from(periodMap.keys()).sort();
    const aggregated: ProfitabilityTrend[] = [];

    periods.forEach((period) => {
      const entry = periodMap.get(period);
      if (!entry || entry.count === 0) {
        return;
      }
      const marginPct = entry.marginPctSum / entry.count;
      aggregated.push({
        contract_id: "portfolio",
        period,
        revenue_zar: entry.revenue,
        cost_zar: entry.cost,
        margin_zar: entry.margin,
        margin_pct: Number(marginPct.toFixed(2)),
        trend: "stable",
      });
    });

    aggregated.forEach((point, index) => {
      if (index === 0) {
        point.trend = "stable";
        return;
      }
      const prev = aggregated[index - 1];
      if (point.margin_pct > prev.margin_pct + 2) {
        point.trend = "improving";
      } else if (point.margin_pct < prev.margin_pct - 2) {
        point.trend = "declining";
      } else {
        point.trend = "stable";
      }
    });

    return aggregated;
  };

  // Fetch portfolio metrics
  useEffect(() => {
    const fetchPortfolioMetrics = async () => {
      try {
        const metrics = await profitabilityApi.getPortfolioMetrics(
          periodRange.start,
          periodRange.end
        );
        setPortfolioMetrics(metrics);
      } catch (err) {
        console.error("Failed to fetch portfolio metrics:", err);
        // Continue with empty state
      }
    };

    fetchPortfolioMetrics();
  }, [periodRange]);

  // Fetch loss leaders
  useEffect(() => {
    const fetchLossLeaders = async () => {
      try {
        const response = await profitabilityApi.getLossLeaders(
          periodRange.start,
          periodRange.end
        );
        setLossLeaders(response.loss_leaders);
      } catch (err) {
        console.error("Failed to fetch loss leaders:", err);
        setLossLeaders([]);
      }
    };

    fetchLossLeaders();
  }, [periodRange]);

  // Fetch all contracts
  useEffect(() => {
    const fetchContracts = async () => {
      try {
        setLoading(true);
        const contractList = await profitabilityApi.getContractList("active");
        const contractDetails = await Promise.all(
          contractList.map((contract) =>
            profitabilityApi.getContractProfitability(
              contract.id,
              periodRange.start,
              periodRange.end
            )
          )
        );
        setContracts(contractDetails);
        setError(null);
      } catch (err) {
        console.error("Failed to fetch contracts:", err);
        setError("Failed to load contracts");
      } finally {
        setLoading(false);
      }
    };

    fetchContracts();
  }, [periodRange]);

  // Fetch trends for selected contract or portfolio
  useEffect(() => {
    const fetchTrends = async () => {
      try {
        if (selectedContractId) {
          const response = await profitabilityApi.getProfitabilityTrends(
            selectedContractId,
            12
          );
          setTrends(response.trends);
        } else if (contracts.length > 0) {
          const responses = await Promise.all(
            contracts.map((contract) =>
              profitabilityApi.getProfitabilityTrends(contract.contract_id, 12)
            )
          );
          const aggregated = aggregatePortfolioTrends(
            responses.map((response) => response.trends)
          );
          setTrends(aggregated);
        } else {
          setTrends([]);
        }
      } catch (err) {
        console.error("Failed to fetch trends:", err);
        setTrends([]);
      }
    };

    fetchTrends();
  }, [selectedContractId, contracts]);

  useEffect(() => {
    const fetchSlaPerformance = async () => {
      if (!selectedContractId) {
        setSlaPerformance([]);
        return;
      }
      try {
        const response = await profitabilityApi.getSLAPerformance(
          selectedContractId,
          12
        );
        setSlaPerformance(response.performance || []);
      } catch (err) {
        console.error("Failed to fetch SLA performance:", err);
        setSlaPerformance([]);
      }
    };

    fetchSlaPerformance();
  }, [selectedContractId]);

  useEffect(() => {
    const fetchReport = async () => {
      if (!selectedContractId) {
        setSelectedReport(null);
        setSelectedAssets([]);
        setReportError(null);
        return;
      }
      try {
        setReportLoading(true);
        const report = await profitabilityApi.getContractProfitabilityReport(
          selectedContractId,
          periodRange.start,
          periodRange.end,
          12
        );
        setSelectedReport(report);
        setSelectedAssets(report.assets || []);
        setReportError(null);
      } catch (err) {
        console.error("Failed to fetch report:", err);
        setReportError("Failed to load contract report");
      } finally {
        setReportLoading(false);
      }
    };

    fetchReport();
  }, [selectedContractId, periodRange]);

  // Sort contracts
  const sortedContracts = useMemo(() => {
    const sorted = [...contracts];
    sorted.sort((a, b) => {
      let aVal: number | string;
      let bVal: number | string;

      switch (sortField) {
        case "margin":
          aVal = a.gross_margin_percentage;
          bVal = b.gross_margin_percentage;
          break;
        case "revenue":
          aVal = a.net_revenue_zar;
          bVal = b.net_revenue_zar;
          break;
        case "status":
          aVal = statusRank(a.status);
          bVal = statusRank(b.status);
          break;
        default:
          return 0;
      }

      if (typeof aVal === "string" && typeof bVal === "string") {
        return sortDirection === "asc"
          ? (aVal as string).localeCompare(bVal as string)
          : (bVal as string).localeCompare(aVal as string);
      }

      return sortDirection === "asc"
        ? (aVal as number) - (bVal as number)
        : (bVal as number) - (aVal as number);
    });
    return sorted;
  }, [contracts, sortField, sortDirection]);

  // Extract unique buildings for dropdown
  const buildings = useMemo(() => {
    const buildingMap = new Map<string, string>();
    contracts.forEach((c) => {
      const id = c.building_id;
      const name = c.building_name || c.building_id || "Unknown";
      if (id && !buildingMap.has(id)) {
        buildingMap.set(id, name);
      }
    });
    return Array.from(buildingMap.entries())
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [contracts]);

  // Filter contracts by search and building
  const filteredContracts = useMemo(() => {
    let filtered = sortedContracts;

    // Filter by building
    if (buildingFilter) {
      filtered = filtered.filter((c) => c.building_id === buildingFilter);
    }

    // Filter by search query
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (c) =>
          c.contract_name.toLowerCase().includes(query) ||
          (c.building_name || c.building_id || "")
            .toLowerCase()
            .includes(query)
      );
    }

    return filtered;
  }, [sortedContracts, searchQuery, buildingFilter]);

  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, periodRange, buildingFilter, contracts.length]);

  const paginatedContracts = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredContracts.slice(start, start + pageSize);
  }, [filteredContracts, currentPage]);

  const totalPages = Math.max(1, Math.ceil(filteredContracts.length / pageSize));

  // Handle sort
  const handleSort = (field: typeof sortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDirection("desc");
    }
  };

  // Render sort icon
  const SortIcon = ({ field }: { field: typeof sortField }) => {
    if (sortField !== field) return null;
    return sortDirection === "asc" ? (
      <ArrowUp className="inline h-3 w-3 ml-1" />
    ) : (
      <ArrowDown className="inline h-3 w-3 ml-1" />
    );
  };

  const handleExportReport = () => {
    if (!selectedReport) return;
    const blob = new Blob([JSON.stringify(selectedReport, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `profitability-report-${selectedReport.contract.code || selectedReport.contract.id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const handleExportFile = async (format: "csv" | "pdf") => {
    if (!selectedContractId) return;
    try {
      const blob = await profitabilityApi.exportContractProfitabilityReport(
        selectedContractId,
        format,
        periodRange.start,
        periodRange.end,
        12
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `profitability-report-${selectedContractId}.${format}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Export failed:", err);
      setReportError(`Export failed (${format.toUpperCase()})`);
    }
  };

  // Loading state
  if (loading) {
    return (
      <PageLoading message="Loading profitability data..." />
    );
  }

  // Error state
  if (error) {
    return (
      <Callout
        title="Error"
        color="rose"
        className="glass-panel"
      >
        {error}
      </Callout>
    );
  }

  return (
    <div className="space-y-6 p-4 md:p-6" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div>
          <Title
            style={{ color: "var(--color-sentinel-text-primary)" }}
            className="text-2xl"
          >
            Profitability Dashboard
          </Title>
          <Text
            style={{ color: "var(--color-sentinel-text-secondary)" }}
            className="text-sm"
          >
            Portfolio financial performance and margin analysis
          </Text>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-3">
          <Select
            value={buildingFilter || "all"}
            onValueChange={(v) =>
              setBuildingFilter(v === "all" ? null : v)
            }
            className="w-48"
          >
            <SelectItem value="all">All Buildings</SelectItem>
            {buildings.map((building) => (
              <SelectItem key={building.id} value={building.id}>
                {building.name}
              </SelectItem>
            ))}
          </Select>

          <Select
            value={periodFilter}
            onValueChange={(v) =>
              setPeriodFilter(v as PeriodOption)
            }
            className="w-40"
          >
            {(["this_month", "last_month", "last_quarter", "ytd"] as const).map(
              (option) => (
                <SelectItem key={option} value={option}>
                  {getPeriodRange(option).label}
                </SelectItem>
              )
            )}
          </Select>

          <Button
            variant="secondary"
            size="sm"
            icon={RefreshCw}
            onClick={() => window.location.reload()}
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* Section 1: Portfolio Overview KPI Cards */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <div className="p-2 rounded" style={{ background: "rgba(59, 130, 246, 0.15)" }}>
            <DollarSign className="h-5 w-5" style={{ color: "var(--color-sentinel-blue)" }} />
          </div>
          <div>
            <h3 className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
              Portfolio Overview
            </h3>
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Key metrics and contract status
            </span>
          </div>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          title="Total Revenue"
          value={
            portfolioMetrics
              ? formatZAR(portfolioMetrics.total_revenue_zar)
              : "R0"
          }
          subtitle={`${portfolioMetrics?.total_contracts || 0} contracts`}
          color="blue"
        />
        <KPICard
          title="Gross Margin"
          value={
            portfolioMetrics
              ? formatZAR(portfolioMetrics.gross_margin_zar)
              : "R0"
          }
          subtitle={
            portfolioMetrics
              ? `Avg ${formatPercent(portfolioMetrics.avg_margin_percentage)}`
              : "0%"
          }
          trend={
            portfolioMetrics && portfolioMetrics.avg_margin_percentage > 0
              ? "up"
              : "neutral"
          }
          color={portfolioMetrics && portfolioMetrics.avg_margin_percentage > 0 ? "green" : "gray"}
        />
        <KPICard
          title="Profitable"
          value={`${portfolioMetrics?.profit_contracts || 0}`}
          subtitle={
            portfolioMetrics && portfolioMetrics.total_contracts > 0
              ? `${Math.round(
                  (portfolioMetrics.profit_contracts /
                    portfolioMetrics.total_contracts) *
                    100
                )}% of portfolio`
              : "0%"
          }
          color="green"
        />
        <KPICard
          title="Loss-Making"
          value={`${portfolioMetrics?.loss_contracts || 0}`}
          subtitle={
            portfolioMetrics && portfolioMetrics.total_contracts > 0
              ? `${Math.round(
                  (portfolioMetrics.loss_contracts /
                    portfolioMetrics.total_contracts) *
                    100
                )}% of portfolio`
              : "0%"
          }
          color={portfolioMetrics && portfolioMetrics.loss_contracts > 0 ? "red" : "gray"}
        />
      </div>

      {/* Section 2: Loss Leaders Alert Panel */}
      {lossLeaders.length > 0 && (
        <div style={{
          background: "rgba(14, 116, 144, 0.05)",
          border: "1px solid var(--color-sentinel-border)",
          borderRadius: "0.5rem",
          padding: "1rem",
          marginTop: "0"
        }}
        >
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="h-5 w-5 text-[var(--color-sentinel-red)]" />
            <h3 style={{ color: "var(--color-sentinel-text-primary)" }} className="font-semibold">
              Loss-Making Contracts Detected
            </h3>
          </div>
          <div className="space-y-2">
            {lossLeaders.slice(0, 3).map((leader) => (
              <div
                key={leader.contract_id}
                className="flex items-center justify-between py-2 px-3 rounded"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                }}
              >
                <div>
                  <Text
                    style={{ color: "var(--color-sentinel-text-primary)" }}
                    className="font-medium"
                  >
                    {leader.contract_name}
                  </Text>
                  <Text
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                    className="text-xs"
                  >
                    {leader.root_causes.join(", ")}
                  </Text>
                </div>
                <div className="text-right">
                  <Text
                    style={{ color: "var(--color-sentinel-red)" }}
                    className="font-semibold"
                  >
                    {formatZAR(leader.loss_amount_zar)}
                  </Text>
                  <Text
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                    className="text-xs block"
                  >
                    {formatPercent(leader.loss_percentage)}
                  </Text>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Section 3: Contract Profitability Table */}
      <div style={{ background: "rgba(14, 116, 144, 0.05)", border: "1px solid var(--color-sentinel-border)", overflow: "hidden", borderRadius: "0.5rem" }}>
        <div
          className="px-4 py-4 flex items-center justify-between"
          style={{
            borderBottom: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(245, 158, 11, 0.15)" }}>
              <AlertTriangle className="h-5 w-5" style={{ color: "var(--color-sentinel-amber)" }} />
            </div>
            <div>
              <h3
                className="text-sm font-medium"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Contract Profitability
              </h3>
              <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Sortable contract details with margins and status
              </span>
            </div>
          </div>

          {/* Search */}
          <input
            type="text"
            placeholder="Search contracts..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="px-3 py-1.5 text-sm rounded"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          />
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
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Contract
                </TableHeaderCell>
                <TableHeaderCell
                  className="cursor-pointer select-none text-right"
                  onClick={() => handleSort("revenue")}
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Revenue
                  <SortIcon field="revenue" />
                </TableHeaderCell>
                <TableHeaderCell
                  className="text-right"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Costs
                </TableHeaderCell>
                <TableHeaderCell
                  className="cursor-pointer select-none text-right"
                  onClick={() => handleSort("margin")}
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Gross Margin
                  <SortIcon field="margin" />
                </TableHeaderCell>
                <TableHeaderCell
                  className="text-right"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Net Margin
                </TableHeaderCell>
                <TableHeaderCell
                  className="cursor-pointer select-none"
                  onClick={() => handleSort("status")}
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Status
                  <SortIcon field="status" />
                </TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {paginatedContracts.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="text-center py-8"
                    style={{ color: "var(--color-sentinel-text-disabled)" }}
                  >
                    {loading
                      ? "Loading contracts..."
                      : searchQuery
                      ? "No contracts found matching your search"
                      : "No contracts available"}
                  </TableCell>
                </TableRow>
              ) : (
                paginatedContracts.map((contract) => (
                  <TableRow
                    key={contract.contract_id}
                    className="cursor-pointer hover:bg-opacity-50 transition-colors"
                    style={{
                      cursor: "pointer",
                      background:
                        selectedContractId === contract.contract_id
                          ? "var(--color-sentinel-bg-secondary)"
                          : undefined,
                    }}
                    onClick={() => setSelectedContractId(contract.contract_id)}
                  >
                    <TableCell
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      <div>
                        <div className="font-medium">
                          {contract.contract_name}
                        </div>
                        <div
                          className="text-xs"
                          style={{ color: "var(--color-sentinel-text-secondary)" }}
                        >
                          {contract.building_name || contract.building_id}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell
                      className="text-right"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      {formatZAR(contract.net_revenue_zar)}
                    </TableCell>
                    <TableCell
                      className="text-right"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      {formatZAR(contract.total_cost_zar)}
                    </TableCell>
                    <TableCell
                      className="text-right"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      <div>
                        <div className="font-medium">
                          {formatZAR(contract.gross_margin_zar)}
                        </div>
                        <div
                          className="text-xs"
                          style={{
                            color:
                              contract.gross_margin_percentage >= 0
                                ? "var(--color-sentinel-green)"
                                : "var(--color-sentinel-red)",
                          }}
                        >
                          {formatPercent(contract.gross_margin_percentage)}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell
                      className="text-right"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      <div>
                        <div className="font-medium">
                          {formatZAR(contract.gross_margin_zar)}
                        </div>
                        <div
                          className="text-xs"
                          style={{
                            color:
                              contract.gross_margin_percentage >= 0
                                ? "var(--color-sentinel-green)"
                                : "var(--color-sentinel-red)",
                          }}
                        >
                          {formatPercent(contract.gross_margin_percentage)}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge
                        color={
                          contract.status === "profitable"
                            ? "emerald"
                            : contract.status === "break_even"
                            ? "amber"
                            : "rose"
                        }
                      >
                        {formatStatusLabel(contract.status)}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-end gap-2">
          <Button
            variant="secondary"
            size="xs"
            disabled={currentPage === 1}
            onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
          >
            Previous
          </Button>
          <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Page {currentPage} of {totalPages}
          </Text>
          <Button
            variant="secondary"
            size="xs"
            disabled={currentPage === totalPages}
            onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
          >
            Next
          </Button>
        </div>
      )}

      {selectedContractId && (
        <div style={{ background: "rgba(14, 116, 144, 0.05)", border: "1px solid var(--color-sentinel-border)", padding: "1.5rem", borderRadius: "0.5rem" }}>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3
                className="text-sm font-medium"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Contract Drill-Down
              </h3>
              <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Asset ROI and contract profitability summary
              </Text>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="xs"
                disabled={!selectedReport || reportLoading}
                onClick={() => handleExportFile("csv")}
              >
                Export CSV
              </Button>
              <Button
                variant="secondary"
                size="xs"
                disabled={!selectedReport || reportLoading}
                onClick={() => handleExportFile("pdf")}
              >
                Export PDF
              </Button>
              <Button
                variant="secondary"
                size="xs"
                disabled={!selectedReport || reportLoading}
                onClick={handleExportReport}
              >
                Export JSON
              </Button>
            </div>
          </div>

          {reportLoading ? (
            <div
              className="h-32 flex items-center justify-center"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            >
              Loading report...
            </div>
          ) : reportError ? (
            <div style={{ border: "1px solid var(--color-sentinel-border)", borderRadius: "0.5rem", padding: "1rem", background: "rgba(14, 116, 144, 0.05)" }}>
              <div className="flex items-center gap-2 mb-2">
                <AlertTriangle className="h-5 w-5" style={{ color: "var(--color-sentinel-red)" }} />
                <h3 style={{ color: "var(--color-sentinel-text-primary)" }} className="font-semibold">
                  Report unavailable
                </h3>
              </div>
              <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {reportError}
              </Text>
            </div>
          ) : selectedReport ? (
            <div className="space-y-4">
              {selectedReport.data_quality_flags.length > 0 && (
                <div style={{ border: "1px solid rgba(245, 158, 11, 0.3)", borderRadius: "0.5rem", padding: "1rem", background: "rgba(245, 158, 11, 0.05)" }}>
                  <div className="flex items-center gap-2 mb-2">
                    <AlertTriangle className="h-5 w-5" style={{ color: "var(--color-sentinel-amber)" }} />
                    <h3 style={{ color: "var(--color-sentinel-text-primary)" }} className="font-semibold">
                      Data quality flags
                    </h3>
                  </div>
                  <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    {selectedReport.data_quality_flags.join(", ")}
                  </Text>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Card style={{ background: "rgba(14, 116, 144, 0.05)", border: "1px solid var(--color-sentinel-border)" }}>
                  <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Net Revenue
                  </Text>
                  <Title className="text-xl" style={{ color: "var(--color-sentinel-text-primary)" }}>
                    {formatZAR(selectedReport.profitability.net_revenue_zar)}
                  </Title>
                </Card>
                <Card style={{ background: "rgba(14, 116, 144, 0.05)", border: "1px solid var(--color-sentinel-border)" }}>
                  <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Total Cost
                  </Text>
                  <Title className="text-xl" style={{ color: "var(--color-sentinel-text-primary)" }}>
                    {formatZAR(selectedReport.profitability.total_cost_zar)}
                  </Title>
                </Card>
                <Card style={{ background: "rgba(14, 116, 144, 0.05)", border: "1px solid var(--color-sentinel-border)" }}>
                  <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Gross Margin
                  </Text>
                  <Title className="text-xl" style={{ color: "var(--color-sentinel-text-primary)" }}>
                    {formatZAR(selectedReport.profitability.gross_margin_zar)}
                  </Title>
                </Card>
                <Card style={{ background: "rgba(14, 116, 144, 0.05)", border: "1px solid var(--color-sentinel-border)" }}>
                  <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Asset Count
                  </Text>
                  <Title className="text-xl" style={{ color: "var(--color-sentinel-text-primary)" }}>
                    {selectedReport.profitability.asset_count}
                  </Title>
                </Card>
              </div>

              <div style={{ border: "1px solid var(--color-sentinel-border)", borderRadius: "0.5rem", overflow: "hidden" }}>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableHeaderCell>Asset</TableHeaderCell>
                      <TableHeaderCell className="text-right">Revenue</TableHeaderCell>
                      <TableHeaderCell className="text-right">Cost</TableHeaderCell>
                      <TableHeaderCell className="text-right">ROI</TableHeaderCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {selectedAssets.length === 0 ? (
                      <TableRow>
                        <TableCell
                          colSpan={4}
                          className="text-center py-6"
                          style={{ color: "var(--color-sentinel-text-disabled)" }}
                        >
                          No asset ROI data available
                        </TableCell>
                      </TableRow>
                    ) : (
                      selectedAssets.map((asset) => (
                        <TableRow key={asset.equipment_id}>
                          <TableCell>
                            <div className="text-sm font-medium">
                              {asset.equipment_name || asset.equipment_code || asset.equipment_id}
                            </div>
                            <div
                              className="text-xs"
                              style={{ color: "var(--color-sentinel-text-secondary)" }}
                            >
                              {asset.equipment_type || "Unknown type"}
                            </div>
                          </TableCell>
                          <TableCell className="text-right">
                            {formatZAR(asset.allocated_revenue_zar)}
                          </TableCell>
                          <TableCell className="text-right">
                            {formatZAR(asset.allocated_cost_zar)}
                          </TableCell>
                          <TableCell className="text-right">
                            <span
                              style={{
                                color:
                                  asset.roi_percentage >= 0
                                    ? "var(--color-sentinel-green)"
                                    : "var(--color-sentinel-red)",
                              }}
                            >
                              {formatPercent(asset.roi_percentage)}
                            </span>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </div>
          ) : null}
        </div>
      )}

      {/* Section 4: Trend Chart */}
      <div style={{ background: "rgba(14, 116, 144, 0.05)", border: "1px solid var(--color-sentinel-border)", padding: "1.5rem", borderRadius: "0.5rem" }}>
        <div className="flex items-center justify-between mb-4">
          <h3
            className="text-sm font-medium"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            Margin Trend
          </h3>
          {selectedContractId && (
            <Button
              variant="light"
              size="xs"
              onClick={() => setSelectedContractId(null)}
            >
              Show Portfolio Average
            </Button>
          )}
        </div>

        {trends.length === 0 ? (
          <div
            className="h-64 flex items-center justify-center"
            style={{ color: "var(--color-sentinel-text-disabled)" }}
          >
            {selectedContractId
              ? "Select a contract to view trends"
              : "No trend data available"}
          </div>
        ) : (
          <div className="h-[300px] min-h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trends}>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="var(--color-sentinel-border)"
                />
                <XAxis
                  dataKey="period"
                  stroke="var(--color-sentinel-text-secondary)"
                  fontSize={12}
                />
                <YAxis
                  stroke="var(--color-sentinel-text-secondary)"
                  fontSize={12}
                  tickFormatter={(value) => `${value}%`}
                />
                <Tooltip
                  contentStyle={{
                    background: "var(--color-sentinel-bg-panel)",
                    border: "1px solid var(--color-sentinel-border)",
                    borderRadius: "4px",
                  }}
                  labelStyle={{ color: "var(--color-sentinel-text-primary)" }}
                  formatter={(value: number) => [`${value.toFixed(1)}%`, "Margin"]}
                />
                <Line
                  type="monotone"
                  dataKey="margin_pct"
                  stroke="var(--color-sentinel-blue)"
                  strokeWidth={2}
                  dot={{ fill: "var(--color-sentinel-blue)", r: 4 }}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Section 5: SLA Penalty Trend */}
      <div style={{ background: "rgba(14, 116, 144, 0.05)", border: "1px solid var(--color-sentinel-border)", padding: "1.5rem", borderRadius: "0.5rem" }}>
        <div className="flex items-center justify-between mb-4">
          <h3
            className="text-sm font-medium"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            SLA Penalty Trend
          </h3>
        </div>

        {!selectedContractId ? (
          <div
            className="h-48 flex items-center justify-center"
            style={{ color: "var(--color-sentinel-text-disabled)" }}
          >
            Select a contract to view SLA penalties
          </div>
        ) : slaPerformance.length === 0 ? (
          <div
            className="h-48 flex items-center justify-center"
            style={{ color: "var(--color-sentinel-text-disabled)" }}
          >
            No SLA penalty data available
          </div>
        ) : (
          <div className="h-[240px] min-h-[240px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={slaPerformance.map((row) => ({
                  period:
                    row.period_start?.toString().slice(0, 7) ||
                    row.period_end?.toString().slice(0, 7) ||
                    "N/A",
                  clawback: row.clawback_amount_zar || 0,
                }))}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="var(--color-sentinel-border)"
                />
                <XAxis
                  dataKey="period"
                  stroke="var(--color-sentinel-text-secondary)"
                  fontSize={12}
                />
                <YAxis
                  stroke="var(--color-sentinel-text-secondary)"
                  fontSize={12}
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
                  dot={{ fill: "var(--color-sentinel-amber)", r: 4 }}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
        <div
          className="text-xs mt-2"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          Units: ZAR per month
        </div>
      </div>
    </div>
  );
}
