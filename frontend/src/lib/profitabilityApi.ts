/**
 * Profitability Analytics API Client
 *
 * Fetches portfolio profitability, contract profitability breakdowns,
 * loss leaders, trends, and asset ROI from backend:
 *  - Portfolio metrics (total revenue, margins, profit/loss counts)
 *  - Per-contract profitability with revenue/cost breakdowns
 *  - Loss leader analysis with root causes
 *  - Monthly profitability trends
 *  - Asset-level ROI calculations
 *
 * Integrates with /api/contracts/profitability/* endpoints.
 */

const RAW_API_BASE_URL = import.meta.env.VITE_API_URL || "";

function resolveApiBaseUrl(): string {
  if (!RAW_API_BASE_URL) return "";
  if (window.location.hostname !== "localhost" && RAW_API_BASE_URL.includes("localhost")) {
    return "";
  }
  return RAW_API_BASE_URL;
}

const isDemoContract = (contractId: string) => contractId.startsWith("demo-");

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("sentinel_token");
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function fetchJson<T>(endpoint: string): Promise<T> {
  const baseUrl = resolveApiBaseUrl();
  const res = await fetch(`${baseUrl}${endpoint}`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const err = await res.json();
      msg = err.detail || err.message || JSON.stringify(err);
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return res.json();
}

// ============= Response Interfaces =============

/**
 * Portfolio-wide profitability metrics
 * Matches backend PortfolioMetrics model.
 */
export interface PortfolioMetrics {
  total_contracts: number;
  total_revenue_zar: number;
  total_cost_zar: number;
  gross_margin_zar: number;
  gross_margin_percentage: number;
  profit_contracts: number;
  loss_contracts: number;
  avg_margin_percentage: number;
  period_start: string;
  period_end: string;
}

/**
 * Per-contract profitability breakdown
 * Matches backend ContractProfitabilityDetail model.
 */
export interface ContractProfitabilityDetail {
  contract_id: string;
  contract_name: string;
  building_id: string;
  building_name?: string | null;
  monthly_revenue_zar: number;
  clawbacks_zar: number;
  net_revenue_zar: number;
  labor_cost_zar: number;
  parts_cost_zar: number;
  subcontractor_cost_zar: number;
  callout_cost_zar: number;
  consumables_cost_zar: number;
  total_cost_zar: number;
  gross_margin_zar: number;
  gross_margin_percentage: number;
  status: "profitable" | "break_even" | "loss";
  mom_change_pct?: number | null;
  ytd_margin_zar?: number | null;
  asset_count: number;
  cost_per_asset_zar: number;
}

/**
 * Monthly profitability trend data point
 * Matches backend ProfitabilityTrend model.
 */
export interface ProfitabilityTrend {
  contract_id: string;
  period: string;
  revenue_zar: number;
  cost_zar: number;
  margin_zar: number;
  margin_pct: number;
  trend: "improving" | "stable" | "declining";
}

export interface SLAPerformanceRecord {
  contract_id: string;
  period_start?: string;
  period_end?: string;
  actual_value: number;
  target_value: number;
  met_target?: boolean;
  clawback_amount_zar?: number;
}

/**
 * Loss-making contract analysis
 * Matches backend LossLeaderAnalysis model.
 */
export interface LossLeaderAnalysis {
  contract_id: string;
  contract_name: string;
  loss_amount_zar: number;
  loss_percentage: number;
  root_causes: string[];
  recommendation: string;
  months_in_loss: number;
  cumulative_loss_zar: number;
}

/**
 * Asset-level ROI calculation
 */
export interface AssetROI {
  contract_id: string;
  equipment_id: string;
  allocated_revenue_zar: number;
  allocated_cost_zar: number;
  margin_zar: number;
  roi_percentage: number;
  coverage_type?: string;
}

export interface AssetROIListItem extends AssetROI {
  equipment_code?: string | null;
  equipment_name?: string | null;
  equipment_type?: string | null;
}

export interface ContractProfitabilityReport {
  contract: {
    id: string;
    code?: string;
    status?: string;
    organization_name?: string | null;
    building_name?: string | null;
  };
  period: {
    start: string;
    end: string;
  };
  profitability: ContractProfitabilityDetail;
  trends: ProfitabilityTrend[];
  assets: AssetROIListItem[];
  data_quality_flags: string[];
  assumptions: string[];
}

/**
 * Minimal contract list item for profitability table.
 */
export interface ContractListItem {
  id: string;
  code?: string;
  building_name?: string | null;
  organization_name?: string | null;
}

// ============= Demo Fallback Data =============

const demoContracts: ContractProfitabilityDetail[] = [
  {
    contract_id: "demo-contract-001",
    contract_name: "CON-DEMO-2024",
    building_id: "demo-building",
    building_name: "Demo Office Tower",
    monthly_revenue_zar: 285000,
    clawbacks_zar: 0,
    net_revenue_zar: 285000,
    labor_cost_zar: 95000,
    parts_cost_zar: 42000,
    subcontractor_cost_zar: 18000,
    callout_cost_zar: 8000,
    consumables_cost_zar: 5000,
    total_cost_zar: 168000,
    gross_margin_zar: 117000,
    gross_margin_percentage: 41.1,
    status: "profitable",
    mom_change_pct: 1.2,
    ytd_margin_zar: 39.5,
    asset_count: 23,
    cost_per_asset_zar: 5087,
  },
  {
    contract_id: "demo-uch-s004",
    contract_name: "CON-UCH-S004-2024",
    building_id: "site-004",
    building_name: "uMhlanga Private Hospital",
    monthly_revenue_zar: 185000,
    clawbacks_zar: 12000,
    net_revenue_zar: 173000,
    labor_cost_zar: 135000,
    parts_cost_zar: 55000,
    subcontractor_cost_zar: 20000,
    callout_cost_zar: 3000,
    consumables_cost_zar: 2000,
    total_cost_zar: 215000,
    gross_margin_zar: -42000,
    gross_margin_percentage: -22.7,
    status: "loss",
    mom_change_pct: -3.1,
    ytd_margin_zar: -14.8,
    asset_count: 49,
    cost_per_asset_zar: 5306,
  },
];

const demoPortfolioMetrics: PortfolioMetrics = {
  total_contracts: demoContracts.length,
  total_revenue_zar: demoContracts.reduce((sum, c) => sum + c.net_revenue_zar, 0),
  total_cost_zar: demoContracts.reduce((sum, c) => sum + c.total_cost_zar, 0),
  gross_margin_zar: demoContracts.reduce((sum, c) => sum + c.gross_margin_zar, 0),
  gross_margin_percentage: 9.2,
  profit_contracts: 1,
  loss_contracts: 1,
  avg_margin_percentage: 9.2,
  period_start: "2026-02-01",
  period_end: "2026-02-28",
};

const demoLossLeaders: LossLeaderAnalysis[] = [
  {
    contract_id: "demo-uch-s004",
    contract_name: "CON-UCH-S004-2024",
    loss_amount_zar: 42000,
    loss_percentage: 22.7,
    root_causes: ["high_labor_costs", "underpriced_contract"],
    recommendation: "Renegotiate rates or reduce scope to restore margin.",
    months_in_loss: 10,
    cumulative_loss_zar: 295000,
  },
];

const demoTrendsByContract: Record<string, ProfitabilityTrend[]> = {
  "demo-site-002": [
    { contract_id: "demo-site-002", period: "2025-11", revenue_zar: 285000, cost_zar: 170000, margin_zar: 115000, margin_pct: 40.4, trend: "stable" },
    { contract_id: "demo-site-002", period: "2025-12", revenue_zar: 285000, cost_zar: 166000, margin_zar: 119000, margin_pct: 41.8, trend: "improving" },
    { contract_id: "demo-site-002", period: "2026-01", revenue_zar: 285000, cost_zar: 167000, margin_zar: 118000, margin_pct: 41.4, trend: "stable" },
    { contract_id: "demo-site-002", period: "2026-02", revenue_zar: 285000, cost_zar: 172000, margin_zar: 113000, margin_pct: 39.6, trend: "declining" },
  ],
  "demo-uch-s004": [
    { contract_id: "demo-uch-s004", period: "2025-11", revenue_zar: 185000, cost_zar: 215000, margin_zar: -30000, margin_pct: -16.2, trend: "declining" },
    { contract_id: "demo-uch-s004", period: "2025-12", revenue_zar: 185000, cost_zar: 217000, margin_zar: -32000, margin_pct: -17.3, trend: "declining" },
    { contract_id: "demo-uch-s004", period: "2026-01", revenue_zar: 185000, cost_zar: 218000, margin_zar: -33000, margin_pct: -17.8, trend: "declining" },
    { contract_id: "demo-uch-s004", period: "2026-02", revenue_zar: 185000, cost_zar: 227000, margin_zar: -42000, margin_pct: -22.7, trend: "declining" },
  ],
};

// ============= API Functions =============

export const profitabilityApi = {
  /**
   * Get portfolio-wide profitability metrics
   * @param period_start - Optional period start date (ISO format)
   * @param period_end - Optional period end date (ISO format)
   */
  getPortfolioMetrics: (period_start?: string, period_end?: string): Promise<PortfolioMetrics> => {
    const params = new URLSearchParams();
    if (period_start) params.set("period_start", period_start);
    if (period_end) params.set("period_end", period_end);
    const qs = params.toString();
    return fetchJson<PortfolioMetrics>(`/api/contracts/profitability/portfolio${qs ? `?${qs}` : ""}`)
      .then((metrics) => (metrics.total_contracts > 0 ? metrics : demoPortfolioMetrics))
      .catch(() => demoPortfolioMetrics);
  },

  /**
   * Get detailed profitability for a single contract
   * @param contractId - Contract ID
   * @param period_start - Optional period start date (ISO format)
   * @param period_end - Optional period end date (ISO format)
   */
  getContractProfitability: (
    contractId: string,
    period_start?: string,
    period_end?: string
  ): Promise<ContractProfitabilityDetail> => {
    if (isDemoContract(contractId)) {
      const fallback = demoContracts.find((contract) => contract.contract_id === contractId);
      return Promise.resolve(fallback || demoContracts[0]);
    }
    const params = new URLSearchParams();
    if (period_start) params.set("period_start", period_start);
    if (period_end) params.set("period_end", period_end);
    const qs = params.toString();
    return fetchJson<ContractProfitabilityDetail>(
      `/api/contracts/profitability/contract/${encodeURIComponent(contractId)}${qs ? `?${qs}` : ""}`
    ).catch(() => {
      const fallback = demoContracts.find((contract) => contract.contract_id === contractId);
      return fallback || demoContracts[0];
    });
  },

  /**
   * Get all loss-making contracts with analysis
   * @param period_start - Optional period start date (ISO format)
   * @param period_end - Optional period end date (ISO format)
   */
  getLossLeaders: (period_start?: string, period_end?: string): Promise<{ loss_leaders: LossLeaderAnalysis[]; count: number }> => {
    const params = new URLSearchParams();
    if (period_start) params.set("period_start", period_start);
    if (period_end) params.set("period_end", period_end);
    const qs = params.toString();
    return fetchJson<{ loss_leaders: LossLeaderAnalysis[]; count: number }>(
      `/api/contracts/profitability/loss-leaders${qs ? `?${qs}` : ""}`
    )
      .then((payload) =>
        payload.loss_leaders.length > 0
          ? payload
          : { loss_leaders: demoLossLeaders, count: demoLossLeaders.length }
      )
      .catch(() => ({ loss_leaders: demoLossLeaders, count: demoLossLeaders.length }));
  },

  /**
   * Get monthly profitability trends for a contract
   * @param contractId - Contract ID
   * @param months - Number of months to fetch (1-24, default 12)
   */
  getProfitabilityTrends: (
    contractId: string,
    months: number = 12
  ): Promise<{ contract_id: string; trends: ProfitabilityTrend[] }> => {
    if (isDemoContract(contractId)) {
      return Promise.resolve({
        contract_id: contractId,
        trends: demoTrendsByContract[contractId] || demoTrendsByContract[demoContracts[0].contract_id],
      });
    }
    return fetchJson<{ contract_id: string; trends: ProfitabilityTrend[] }>(
      `/api/contracts/profitability/trends/${encodeURIComponent(contractId)}?months=${months}`
    )
      .then((response) =>
        response.trends.length > 0
          ? response
          : {
              contract_id: contractId,
              trends: demoTrendsByContract[contractId] || demoTrendsByContract[demoContracts[0].contract_id],
            }
      )
      .catch(() => ({
        contract_id: contractId,
        trends: demoTrendsByContract[contractId] || demoTrendsByContract[demoContracts[0].contract_id],
      }));
  },

  /**
   * Get SLA performance history for a contract
   */
  getSLAPerformance: (
    contractId: string,
    months: number = 12
  ): Promise<{ contract_id: string; months: number; performance: SLAPerformanceRecord[] }> => {
    return fetchJson<{ contract_id: string; months: number; performance: SLAPerformanceRecord[] }>(
      `/api/contracts/sla/performance/${encodeURIComponent(contractId)}?months=${months}`
    ).catch(() => ({
      contract_id: contractId,
      months,
      performance: [],
    }));
  },

  /**
   * Get ROI calculation for a specific asset
   * @param contractId - Contract ID
   * @param equipmentId - Equipment ID
   * @param period_start - Optional period start date (ISO format)
   * @param period_end - Optional period end date (ISO format)
   */
  getAssetROI: (
    contractId: string,
    equipmentId: string,
    period_start?: string,
    period_end?: string
  ): Promise<AssetROI> => {
    const params = new URLSearchParams();
    if (period_start) params.set("period_start", period_start);
    if (period_end) params.set("period_end", period_end);
    const qs = params.toString();
    return fetchJson<AssetROI>(
      `/api/contracts/profitability/asset-roi/${encodeURIComponent(contractId)}/${encodeURIComponent(equipmentId)}${qs ? `?${qs}` : ""}`
    ).catch(() => ({
      contract_id: contractId,
      equipment_id: equipmentId,
      allocated_revenue_zar: 0,
      allocated_cost_zar: 0,
      margin_zar: 0,
      roi_percentage: 0,
    }));
  },

  /**
   * Get ROI list for all assets in a contract
   * @param contractId - Contract ID
   * @param period_start - Optional period start date (ISO format)
   * @param period_end - Optional period end date (ISO format)
   * @param limit - Optional asset limit
   */
  getContractAssetROIList: (
    contractId: string,
    period_start?: string,
    period_end?: string,
    limit?: number
  ): Promise<{ contract_id: string; assets: AssetROIListItem[]; count: number }> => {
    const params = new URLSearchParams();
    if (period_start) params.set("period_start", period_start);
    if (period_end) params.set("period_end", period_end);
    if (limit) params.set("limit", `${limit}`);
    const qs = params.toString();
    return fetchJson<{ contract_id: string; assets: AssetROIListItem[]; count: number }>(
      `/api/contracts/profitability/assets/${encodeURIComponent(contractId)}${qs ? `?${qs}` : ""}`
    ).catch(() => ({ contract_id: contractId, assets: [], count: 0 }));
  },

  /**
   * Get profitability report for a contract
   * @param contractId - Contract ID
   * @param period_start - Optional period start date (ISO format)
   * @param period_end - Optional period end date (ISO format)
   * @param asset_limit - Optional asset list limit
   */
  getContractProfitabilityReport: (
    contractId: string,
    period_start?: string,
    period_end?: string,
    asset_limit?: number
  ): Promise<ContractProfitabilityReport> => {
    const params = new URLSearchParams();
    if (period_start) params.set("period_start", period_start);
    if (period_end) params.set("period_end", period_end);
    if (asset_limit) params.set("asset_limit", `${asset_limit}`);
    const qs = params.toString();
    return fetchJson<ContractProfitabilityReport>(
      `/api/contracts/profitability/report/${encodeURIComponent(contractId)}${qs ? `?${qs}` : ""}`
    ).catch(() => ({
      contract: { id: contractId },
      period: { start: period_start || "", end: period_end || "" },
      profitability: demoContracts[0],
      trends: demoTrendsByContract[demoContracts[0].contract_id] || [],
      assets: [],
      data_quality_flags: ["report_unavailable"],
      assumptions: [],
    }));
  },

  /**
   * Export profitability report as CSV or PDF
   * @param contractId - Contract ID
   * @param format - csv or pdf
   * @param period_start - Optional period start date (ISO format)
   * @param period_end - Optional period end date (ISO format)
   * @param asset_limit - Optional asset list limit
   */
  exportContractProfitabilityReport: async (
    contractId: string,
    format: "csv" | "pdf",
    period_start?: string,
    period_end?: string,
    asset_limit?: number
  ): Promise<Blob> => {
    const baseUrl = resolveApiBaseUrl();
    const params = new URLSearchParams();
    params.set("format", format);
    if (period_start) params.set("period_start", period_start);
    if (period_end) params.set("period_end", period_end);
    if (asset_limit) params.set("asset_limit", `${asset_limit}`);
    const qs = params.toString();
    const res = await fetch(
      `${baseUrl}/api/contracts/profitability/report/${encodeURIComponent(contractId)}/export?${qs}`,
      { headers: authHeaders() }
    );
    if (!res.ok) {
      throw new Error(`Export failed: ${res.statusText}`);
    }
    return res.blob();
  },

  /**
   * Get list of contracts for profitability table (IDs and labels).
   */
  getContractList: async (status: string = "active"): Promise<ContractListItem[]> => {
    try {
      const params = new URLSearchParams();
      if (status) params.set("status", status);
      const qs = params.toString();
      const response = await fetchJson<{ contracts: any[] }>(
        `/api/contracts${qs ? `?${qs}` : ""}`
      );
      if (!response.contracts || response.contracts.length === 0) {
        return demoContracts.map((contract) => ({
          id: contract.contract_id,
          code: contract.contract_name,
          building_name: contract.building_name,
        }));
      }
      return response.contracts.map((contract) => ({
        id: contract.id,
        code: contract.code,
        building_name: contract.buildings?.name ?? null,
        organization_name: contract.organizations?.name ?? null,
      }));
    } catch {
      return demoContracts.map((contract) => ({
        id: contract.contract_id,
        code: contract.contract_name,
        building_name: contract.building_name,
      }));
    }
  },
};
