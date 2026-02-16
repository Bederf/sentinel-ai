/**
 * BudgetReportPage - Budget reporting and export
 */

import { useEffect, useState } from "react";
import {
  Card,
  Title,
  Text,
  Select,
  SelectItem,
  Button,
} from "@tremor/react";
import {
  Table,
  TableHead,
  TableRow,
  TableHeaderCell,
  TableBody,
  TableCell,
} from "@tremor/react";
import { FileText } from "lucide-react";
import { PageLoading } from "../components/PageLoading";
import type { Contract, BudgetReport } from "../lib/contractApi";

export function BudgetReportPage() {
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [selectedContractId, setSelectedContractId] = useState<string>("");
  const [year, setYear] = useState<number>(new Date().getFullYear());
  const [month, setMonth] = useState<number | null>(null);
  const [report, setReport] = useState<BudgetReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const formatZAR = (amount: number) => {
    return new Intl.NumberFormat("en-ZA", {
      style: "currency",
      currency: "ZAR",
      maximumFractionDigits: 0,
    }).format(amount);
  };

  useEffect(() => {
    const loadContracts = async () => {
      setLoading(true);
      try {
        // Add delay to prevent concurrent requests hitting rate limiter
        await new Promise((resolve) => setTimeout(resolve, 600));
        const { contractApi } = await import("../lib/contractApi");
        const data = await contractApi.getContracts({ status: "active" });
        setContracts(data);
        if (!selectedContractId && data.length > 0) {
          setSelectedContractId(data[0].id || data[0].contract_code);
        }
      } catch (err) {
        setError("Failed to load contracts");
      } finally {
        setLoading(false);
      }
    };

    loadContracts();
  }, []);

  useEffect(() => {
    const loadReport = async () => {
      if (!selectedContractId) {
        setReport(null);
        return;
      }
      try {
        const { contractApi } = await import("../lib/contractApi");
        const data = await contractApi.getBudgetReportByMonth(
          selectedContractId,
          year,
          month || undefined
        );
        setReport(data);
        setError(null);
      } catch (err) {
        setError("Failed to load budget report");
        setReport(null);
      }
    };

    loadReport();
  }, [selectedContractId, year, month]);

  const handleExport = async (format: "csv" | "pdf" | "json") => {
    if (!selectedContractId) return;
    try {
      const { contractApi } = await import("../lib/contractApi");
      if (format === "json") {
        if (!report) return;
        const blob = new Blob([JSON.stringify(report, null, 2)], {
          type: "application/json",
        });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `budget-report-${selectedContractId}-${year}${month ? `-${month}` : ""}.json`;
        link.click();
        URL.revokeObjectURL(url);
        return;
      }

      const blob = await contractApi.exportBudgetReport(
        selectedContractId,
        year,
        format,
        month || undefined
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `budget-report-${selectedContractId}-${year}${month ? `-${month}` : ""}.${format}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(`Failed to export ${format.toUpperCase()}`);
    }
  };

  if (loading) {
    return <PageLoading message="Loading budget reports..." />;
  }

  return (
    <div className="space-y-6 p-4 md:p-6" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <Title style={{ color: "var(--color-sentinel-text-primary)" }}>
            Budget Reports
          </Title>
          <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Contract budget summary with monthly and equipment-type breakdowns.
          </Text>
        </div>
        <div className="flex items-center gap-2">
          <Button size="xs" variant="secondary" onClick={() => handleExport("csv")}>
            Export CSV
          </Button>
          <Button size="xs" variant="secondary" onClick={() => handleExport("pdf")}>
            Export PDF
          </Button>
          <Button size="xs" variant="secondary" onClick={() => handleExport("json")}>
            Export JSON
          </Button>
        </div>
      </div>

      <Card style={{ background: "rgba(14, 116, 144, 0.05)", border: "1px solid var(--color-sentinel-border)" }}>
        {/* Filters Header */}
        <div className="pb-4 mb-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
          <div className="flex items-center gap-2 mb-4">
            <div className="p-2 rounded" style={{ background: "rgba(59, 130, 246, 0.15)" }}>
              <FileText className="h-4 w-4" style={{ color: "var(--color-sentinel-blue)" }} />
            </div>
            <div>
              <h3 className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Filter Reports
              </h3>
              <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Select contract, year, and month
              </span>
            </div>
          </div>
        </div>
        <div className="flex flex-col lg:flex-row lg:items-center gap-4">
          <div className="flex-1 min-w-0">
            <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Contract
            </Text>
            <Select value={selectedContractId} onValueChange={setSelectedContractId}>
              {contracts.map((contract) => (
                <SelectItem
                  key={contract.id || contract.contract_code}
                  value={contract.id || contract.contract_code}
                >
                  {contract.contract_code} · {contract.organization.name}
                </SelectItem>
              ))}
            </Select>
          </div>
          <div className="w-32 lg:w-40">
            <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Year
            </Text>
            <Select value={`${year}`} onValueChange={(value) => setYear(Number(value))}>
              {[year - 1, year, year + 1].map((y) => (
                <SelectItem key={y} value={`${y}`}>
                  {y}
                </SelectItem>
              ))}
            </Select>
          </div>
          <div className="w-40">
            <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Month
            </Text>
            <Select value={month ? `${month}` : "all"} onValueChange={(value) => {
              if (value === "all") {
                setMonth(null);
              } else {
                setMonth(Number(value));
              }
            }}>
              <SelectItem value="all">All</SelectItem>
              {Array.from({ length: 12 }, (_, idx) => idx + 1).map((m) => (
                <SelectItem key={m} value={`${m}`}>
                  {m}
                </SelectItem>
              ))}
            </Select>
          </div>
        </div>
      </Card>

      {error && (
        <Card style={{ background: "rgba(14, 116, 144, 0.05)", border: "1px solid var(--color-sentinel-border)" }}>
          <Text style={{ color: "var(--color-sentinel-red)" }}>{error}</Text>
        </Card>
      )}

      {report && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card style={{ background: "rgba(14, 116, 144, 0.05)", border: "1px solid var(--color-sentinel-border)" }}>
            <div className="flex items-start justify-between">
              <div>
                <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Total Budget
                </Text>
                <Title style={{ color: "var(--color-sentinel-text-primary)" }}>
                  {formatZAR(report.totals.total_budget_zar)}
                </Title>
              </div>
              <div className="p-2 rounded" style={{ background: "rgba(59, 130, 246, 0.15)" }}>
                <FileText className="h-5 w-5" style={{ color: "var(--color-sentinel-blue)" }} />
              </div>
            </div>
          </Card>
          <Card style={{ background: "rgba(14, 116, 144, 0.05)", border: "1px solid var(--color-sentinel-border)" }}>
            <div className="flex items-start justify-between">
              <div>
                <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Total Actual
                </Text>
                <Title style={{ color: "var(--color-sentinel-text-primary)" }}>
                  {formatZAR(report.totals.total_actual_zar)}
                </Title>
              </div>
              <div className="p-2 rounded" style={{ background: "rgba(245, 158, 11, 0.15)" }}>
                <FileText className="h-5 w-5" style={{ color: "var(--color-sentinel-amber)" }} />
              </div>
            </div>
          </Card>
          <Card style={{ background: "rgba(14, 116, 144, 0.05)", border: "1px solid var(--color-sentinel-border)" }}>
            <div className="flex items-start justify-between">
              <div>
                <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Variance
                </Text>
                <Title style={{ color: "var(--color-sentinel-text-primary)" }}>
                  {formatZAR(report.totals.variance_zar)}
                </Title>
              </div>
              <div className="p-2 rounded" style={{ background: "rgba(16, 185, 129, 0.15)" }}>
                <FileText className="h-5 w-5" style={{ color: "var(--color-sentinel-green)" }} />
              </div>
            </div>
          </Card>
        </div>
      )}

      {report && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card style={{ background: "rgba(14, 116, 144, 0.05)", border: "1px solid var(--color-sentinel-border)" }}>
            {/* Section Header */}
            <div className="pb-3 mb-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
              <div className="flex items-center gap-2">
                <div className="p-2 rounded" style={{ background: "rgba(59, 130, 246, 0.15)" }}>
                  <FileText className="h-4 w-4" style={{ color: "var(--color-sentinel-blue)" }} />
                </div>
                <div>
                  <h3 className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                    Monthly Breakdown
                  </h3>
                </div>
              </div>
            </div>
            <Table>
              <TableHead>
                <TableRow>
                  <TableHeaderCell>Month</TableHeaderCell>
                  <TableHeaderCell className="text-right">Budget</TableHeaderCell>
                  <TableHeaderCell className="text-right">Actual</TableHeaderCell>
                  <TableHeaderCell className="text-right">Spend %</TableHeaderCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {report.monthly.map((row) => (
                  <TableRow key={row.month}>
                    <TableCell>{row.month}</TableCell>
                    <TableCell className="text-right">{formatZAR(row.total_budget_zar)}</TableCell>
                    <TableCell className="text-right">{formatZAR(row.total_actual_zar)}</TableCell>
                    <TableCell className="text-right">{row.spend_percentage.toFixed(1)}%</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>

          <Card style={{ background: "rgba(14, 116, 144, 0.05)", border: "1px solid var(--color-sentinel-border)" }}>
            {/* Section Header */}
            <div className="pb-3 mb-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
              <div className="flex items-center gap-2">
                <div className="p-2 rounded" style={{ background: "rgba(245, 158, 11, 0.15)" }}>
                  <FileText className="h-4 w-4" style={{ color: "var(--color-sentinel-amber)" }} />
                </div>
                <div>
                  <h3 className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                    Equipment-Type Breakdown
                  </h3>
                </div>
              </div>
            </div>
            {report.equipment_type_breakdown.length === 0 ? (
              <Text className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                No equipment-type budgets available.
              </Text>
            ) : (
              <Table>
                <TableHead>
                  <TableRow>
                    <TableHeaderCell>Type</TableHeaderCell>
                    <TableHeaderCell className="text-right">Budget</TableHeaderCell>
                    <TableHeaderCell className="text-right">Actual</TableHeaderCell>
                    <TableHeaderCell className="text-right">Spend %</TableHeaderCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {report.equipment_type_breakdown.map((row) => (
                    <TableRow key={row.equipment_type}>
                      <TableCell>{row.equipment_type}</TableCell>
                      <TableCell className="text-right">{formatZAR(row.total_budget_zar)}</TableCell>
                      <TableCell className="text-right">{formatZAR(row.total_actual_zar)}</TableCell>
                      <TableCell className="text-right">{row.spend_percentage.toFixed(1)}%</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
