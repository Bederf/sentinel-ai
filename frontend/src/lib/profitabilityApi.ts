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

const API_BASE_URL = import.meta.env.VITE_API_URL || "";

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("sentinel_token");
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function fetchJson<T>(endpoint: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
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
 */
export interface PortfolioMetrics {
  total_contracts: number;
  total_revenue: number; // ZAR
  total_costs: number; // ZAR
  gross_margin: number; // ZAR
  profit_count: number; // Contracts with positive margin
  loss_count: number; // Contracts with negative margin
  avg_margin_pct: number; // Average margin percentage
  period_start: string; // ISO date
  period_end: string; // ISO date
}

/**
 * Per-contract profitability breakdown
 */
export interface ContractProfitabilityDetail {
  contract_id: string;
  organization_name: string;
  building_name: string;
  revenue: {
    monthly_fee: number;
    clawbacks: number;
    net_revenue: number;
  };
  costs: {
    labor: number;
    parts: number;
    subcontractor: number;
    callout: number;
    consumables: number;
    total_costs: number;
  };
  gross_margin: number; // ZAR
  net_margin: number; // ZAR
  margin_pct: number; // Percentage
  status: "profitable" | "break-even" | "loss-making";
  trends: {
    mom_change_pct: number; // Month-over-month change
    ytd_margin: number; // Year-to-date margin %
    trend_indicator: "improving" | "stable" | "declining";
  };
  assets: {
    count: number;
    cost_per_asset: number; // Average cost per asset
  };
}

/**
 * Monthly profitability trend data point
 */
export interface ProfitabilityTrend {
  period: string; // YYYY-MM format
  revenue: number; // ZAR
  costs: number; // ZAR
  margin: number; // ZAR
  margin_pct: number; // Percentage
  trend_indicator: "improving" | "stable" | "declining";
}

/**
 * Loss-making contract analysis
 */
export interface LossLeaderAnalysis {
  contract_id: string;
  organization_name: string;
  building_name: string;
  loss_amount: number; // ZAR (negative value)
  loss_pct: number; // Percentage loss
  root_causes: string[]; // e.g., ["high_labor_costs", "underpriced_contract"]
  recommendation: string; // Actionable recommendation
  months_in_loss: number; // Consecutive months in loss
  cumulative_loss: number; // Total loss over period (ZAR)
}

/**
 * Asset-level ROI calculation
 */
export interface AssetROI {
  contract_id: string;
  equipment_id: string;
  equipment_name: string;
  revenue_allocation: number; // Portion of revenue allocated to this asset
  cost_allocation: number; // Portion of costs allocated to this asset
  margin: number; // ZAR
  roi_pct: number; // ROI percentage
  period_start: string;
  period_end: string;
}

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
    return fetchJson(`/api/contracts/profitability/portfolio${qs ? `?${qs}` : ""}`);
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
    const params = new URLSearchParams();
    if (period_start) params.set("period_start", period_start);
    if (period_end) params.set("period_end", period_end);
    const qs = params.toString();
    return fetchJson(
      `/api/contracts/profitability/contract/${encodeURIComponent(contractId)}${qs ? `?${qs}` : ""}`
    );
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
    return fetchJson(`/api/contracts/profitability/loss-leaders${qs ? `?${qs}` : ""}`);
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
    return fetchJson(
      `/api/contracts/profitability/trends/${encodeURIComponent(contractId)}?months=${months}`
    );
  },

  /**
   * Get ROI calculation for a specific asset
   * @param contractId - Contract ID
   * @param equipmentId - Equipment ID
   */
  getAssetROI: (contractId: string, equipmentId: string): Promise<AssetROI> => {
    return fetchJson(
      `/api/contracts/profitability/asset-roi/${encodeURIComponent(contractId)}/${encodeURIComponent(equipmentId)}`
    );
  },
};
