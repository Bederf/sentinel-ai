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
  DollarSign,
  TrendingUp,
  TrendingDown,
  Minus,
  AlertTriangle,
  Calendar,
  RefreshCw,
  ArrowUp,
  ArrowDown,
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
    <Card className="glass-panel">
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

  // UI state
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [periodFilter, setPeriodFilter] = useState<PeriodOption>("this_month");
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

  // Filter contracts by search
  const filteredContracts = useMemo(() => {
    if (!searchQuery) return sortedContracts;
    const query = searchQuery.toLowerCase();
    return sortedContracts.filter(
      (c) =>
        c.contract_name.toLowerCase().includes(query) ||
        (c.building_name || c.building_id || "")
          .toLowerCase()
          .includes(query)
    );
  }, [sortedContracts, searchQuery]);

  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, periodRange, contracts.length]);

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
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
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

        {/* Period Filter */}
        <div className="flex items-center gap-3">
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
        <Callout
          title="Loss-Making Contracts Detected"
          icon={AlertTriangle}
          color="rose"
          className="glass-panel"
        >
          <div className="space-y-2 mt-3">
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
        </Callout>
      )}

      {/* Section 3: Contract Profitability Table */}
      <div className="glass-panel overflow-hidden">
        <div
          className="px-4 py-3 flex items-center justify-between"
          style={{
            borderBottom: "1px solid var(--color-sentinel-border)",
          }}
        >
          <h3
            className="text-sm font-medium"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            Contract Profitability
          </h3>

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

      {/* Section 4: Trend Chart */}
      <div className="glass-panel p-6">
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
    </div>
  );
}
