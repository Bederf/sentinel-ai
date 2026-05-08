/**
 * BudgetReportPage - Budget reporting and export
 */

import { useEffect, useState } from "react";
import { FileText, DollarSign, TrendingUp, TrendingDown } from "lucide-react";
import { PageLoading } from "../components/PageLoading";
import { Panel } from "../components/Panel";
import { KPICard } from "../components/KPICard";
import { EmptyState } from "../components/EmptyState";
import type { Contract, BudgetReport } from "../lib/contractApi";

const SELECT_STYLE: React.CSSProperties = {
  background: "var(--color-sentinel-bg-secondary)",
  border: "1px solid var(--color-sentinel-border)",
  color: "var(--color-sentinel-text-primary)",
};

export function BudgetReportPage() {
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [selectedContractId, setSelectedContractId] = useState<string>("");
  const [year, setYear] = useState<number>(new Date().getFullYear());
  const [month, setMonth] = useState<number | null>(null);
  const [report, setReport] = useState<BudgetReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const formatZAR = (amount: number) =>
    new Intl.NumberFormat("en-ZA", {
      style: "currency",
      currency: "ZAR",
      maximumFractionDigits: 0,
    }).format(amount);

  useEffect(() => {
    const loadContracts = async () => {
      setLoading(true);
      try {
        // Delay prevents concurrent requests hitting rate limiter on mount
        await new Promise((resolve) => setTimeout(resolve, 600));
        const { contractApi } = await import("../lib/contractApi");
        const data = await contractApi.getContracts({ status: "active" });
        setContracts(data);
        if (!selectedContractId && data.length > 0) {
          setSelectedContractId(data[0].id || data[0].contract_code);
        }
      } catch {
        setError("Failed to load contracts");
      } finally {
        setLoading(false);
      }
    };
    loadContracts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const loadReport = async () => {
      if (!selectedContractId) { setReport(null); return; }
      try {
        const { contractApi } = await import("../lib/contractApi");
        const data = await contractApi.getBudgetReportByMonth(
          selectedContractId,
          year,
          month || undefined
        );
        setReport(data);
        setError(null);
      } catch {
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
        const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `budget-report-${selectedContractId}-${year}${month ? `-${month}` : ""}.json`;
        a.click();
        URL.revokeObjectURL(url);
        return;
      }
      const blob = await contractApi.exportBudgetReport(selectedContractId, year, format, month || undefined);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `budget-report-${selectedContractId}-${year}${month ? `-${month}` : ""}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(`Failed to export ${format.toUpperCase()}`);
    }
  };

  const variance = report?.totals.variance_zar ?? 0;

  return (
    <div
      className="h-full overflow-y-auto"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      {loading ? (
        <PageLoading message="Loading budget reports…" />
      ) : (
        <div className="space-y-6 p-4 md:p-6">

          {/* Page header + export actions */}
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <h1
                className="text-xl font-semibold"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Budget Reports
              </h1>
              <p className="text-sm mt-0.5" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Contract budget summary with monthly and equipment-type breakdowns.
              </p>
            </div>
            <div className="flex items-center gap-2">
              {(["csv", "pdf", "json"] as const).map((fmt) => (
                <button
                  key={fmt}
                  onClick={() => handleExport(fmt)}
                  className="px-3 py-1.5 rounded text-xs font-medium transition-colors hover:opacity-80"
                  style={{
                    background: "var(--color-sentinel-bg-secondary)",
                    border: "1px solid var(--color-sentinel-border)",
                    color: "var(--color-sentinel-text-primary)",
                  }}
                >
                  Export {fmt.toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          {/* Filters */}
          <Panel
            header={{
              icon: <FileText className="h-4 w-4" />,
              title: "Filter Reports",
              accentColor: "var(--color-sentinel-blue)",
            }}
          >
            <div className="p-4 flex flex-col lg:flex-row lg:items-end gap-4">
              <div className="flex-1 min-w-0">
                <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Contract
                </label>
                <select
                  value={selectedContractId}
                  onChange={(e) => setSelectedContractId(e.target.value)}
                  className="w-full rounded appearance-none cursor-pointer px-3 py-2 text-sm focus:outline-none"
                  style={SELECT_STYLE}
                  aria-label="Select contract"
                >
                  {contracts.map((c) => (
                    <option key={c.id || c.contract_code} value={c.id || c.contract_code}>
                      {c.contract_code} · {c.organization.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="w-32">
                <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Year
                </label>
                <select
                  value={`${year}`}
                  onChange={(e) => setYear(Number(e.target.value))}
                  className="w-full rounded appearance-none cursor-pointer px-3 py-2 text-sm focus:outline-none"
                  style={SELECT_STYLE}
                  aria-label="Select year"
                >
                  {[year - 1, year, year + 1].map((y) => (
                    <option key={y} value={`${y}`}>{y}</option>
                  ))}
                </select>
              </div>
              <div className="w-40">
                <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Month
                </label>
                <select
                  value={month ? `${month}` : "all"}
                  onChange={(e) => setMonth(e.target.value === "all" ? null : Number(e.target.value))}
                  className="w-full rounded appearance-none cursor-pointer px-3 py-2 text-sm focus:outline-none"
                  style={SELECT_STYLE}
                  aria-label="Select month"
                >
                  <option value="all">All</option>
                  {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                    <option key={m} value={`${m}`}>{m}</option>
                  ))}
                </select>
              </div>
            </div>
          </Panel>

          {/* Error banner */}
          {error && (
            <div
              className="rounded px-4 py-3 text-sm"
              style={{
                background: "rgba(220,38,38,0.08)",
                border: "1px solid rgba(220,38,38,0.25)",
                color: "var(--color-sentinel-red)",
              }}
            >
              {error}
            </div>
          )}

          {/* KPI summary */}
          {report && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <KPICard
                title="Total Budget"
                value={formatZAR(report.totals.total_budget_zar)}
                icon={<DollarSign className="h-5 w-5" />}
                accentColor="blue"
              />
              <KPICard
                title="Total Actual"
                value={formatZAR(report.totals.total_actual_zar)}
                icon={<DollarSign className="h-5 w-5" />}
                accentColor="orange"
              />
              <KPICard
                title="Variance"
                value={formatZAR(variance)}
                icon={variance >= 0 ? <TrendingUp className="h-5 w-5" /> : <TrendingDown className="h-5 w-5" />}
                accentColor={variance >= 0 ? "green" : "red"}
              />
            </div>
          )}

          {/* Breakdown tables */}
          {report && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

              {/* Monthly Breakdown */}
              <Panel
                header={{
                  icon: <FileText className="h-4 w-4" />,
                  title: "Monthly Breakdown",
                  accentColor: "var(--color-sentinel-blue)",
                }}
              >
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr style={{ borderBottom: "1px solid var(--color-sentinel-border)", background: "var(--color-sentinel-bg-secondary)" }}>
                        {["Month", "Budget", "Actual", "Spend %"].map((h, i) => (
                          <th
                            key={h}
                            className={`px-4 py-2 text-xs font-medium ${i === 0 ? "text-left" : "text-right"}`}
                            style={{ color: "var(--color-sentinel-text-secondary)" }}
                          >
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {report.monthly.map((row) => (
                        <tr key={row.month} style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}>
                          <td className="px-4 py-2.5" style={{ color: "var(--color-sentinel-text-primary)" }}>
                            {row.month}
                          </td>
                          <td className="px-4 py-2.5 text-right tabular-nums" style={{ color: "var(--color-sentinel-text-primary)" }}>
                            {formatZAR(row.total_budget_zar)}
                          </td>
                          <td className="px-4 py-2.5 text-right tabular-nums" style={{ color: "var(--color-sentinel-text-primary)" }}>
                            {formatZAR(row.total_actual_zar)}
                          </td>
                          <td className="px-4 py-2.5 text-right tabular-nums" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                            {row.spend_percentage.toFixed(1)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Panel>

              {/* Equipment-Type Breakdown */}
              <Panel
                header={{
                  icon: <FileText className="h-4 w-4" />,
                  title: "Equipment-Type Breakdown",
                  accentColor: "var(--color-sentinel-amber)",
                }}
              >
                {report.equipment_type_breakdown.length === 0 ? (
                  <div className="p-6">
                    <EmptyState
                      icon={FileText}
                      title="No equipment data"
                      subtext="No equipment-type budgets available for this period."
                    />
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--color-sentinel-border)", background: "var(--color-sentinel-bg-secondary)" }}>
                          {["Type", "Budget", "Actual", "Spend %"].map((h, i) => (
                            <th
                              key={h}
                              className={`px-4 py-2 text-xs font-medium ${i === 0 ? "text-left" : "text-right"}`}
                              style={{ color: "var(--color-sentinel-text-secondary)" }}
                            >
                              {h}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {report.equipment_type_breakdown.map((row) => (
                          <tr key={row.equipment_type} style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}>
                            <td className="px-4 py-2.5" style={{ color: "var(--color-sentinel-text-primary)" }}>
                              {row.equipment_type}
                            </td>
                            <td className="px-4 py-2.5 text-right tabular-nums" style={{ color: "var(--color-sentinel-text-primary)" }}>
                              {formatZAR(row.total_budget_zar)}
                            </td>
                            <td className="px-4 py-2.5 text-right tabular-nums" style={{ color: "var(--color-sentinel-text-primary)" }}>
                              {formatZAR(row.total_actual_zar)}
                            </td>
                            <td className="px-4 py-2.5 text-right tabular-nums" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                              {row.spend_percentage.toFixed(1)}%
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Panel>

            </div>
          )}

        </div>
      )}
    </div>
  );
}
