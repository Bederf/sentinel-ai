/**
 * Contract Management API Client
 *
 * Fetches contract, SLA, budget, and assessment data from backend:
 *  - Organizations (FM clients)
 *  - Contracts (full maintenance, ad-hoc, etc.)
 *  - SLA terms & compliance
 *  - Budget tracking & variance
 *  - Condition assessments
 *
 * Falls back to local JSON data when API not available.
 */

const RAW_API_BASE_URL = import.meta.env.VITE_API_URL || "";

function resolveApiBaseUrl(): string {
  // In production (non-localhost), always use relative paths for API calls
  // This ensures requests go to the same domain/port as the frontend
  if (window.location.hostname !== "localhost") {
    return "";
  }
  // In development, use VITE_API_URL if set
  if (!RAW_API_BASE_URL) return "";
  if (RAW_API_BASE_URL.includes("localhost")) {
    return RAW_API_BASE_URL;
  }
  return "";
}

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

async function postJson<T>(endpoint: string, data: unknown): Promise<T> {
  const baseUrl = resolveApiBaseUrl();
  const res = await fetch(`${baseUrl}${endpoint}`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(data),
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

async function patchJson<T>(endpoint: string, data?: unknown): Promise<T> {
  const baseUrl = resolveApiBaseUrl();
  const res = await fetch(`${baseUrl}${endpoint}`, {
    method: "PATCH",
    headers: authHeaders(),
    ...(data ? { body: JSON.stringify(data) } : {}),
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

export interface Organization {
  code: string;
  name: string;
  tier: string;
  primary_contact_name: string;
  primary_contact_email: string;
  primary_contact_phone: string;
}

export interface Contract {
  id?: string;
  contract_code: string;
  organization: Organization;
  contract: {
    type: string;
    status: string;
    start_date: string;
    end_date: string;
    auto_renew: boolean;
    monthly_fee_zar: number;
    pricing_basis: string;
    payment_terms: string;
    billing_cycle_days: number;
  };
  sla_terms: SLATerm[];
  budget: Budget;
  condition_assessment: ConditionAssessment;
  profitability_snapshot: ProfitabilitySnapshot;
}

function buildFallbackContract(base?: Partial<Contract>): Contract {
  const now = new Date();
  const year = now.getFullYear();
  return {
    id: base?.id,
    contract_code: base?.contract_code || "CON-DEMO-0001",
    organization: base?.organization || {
      code: "ORG-DEMO",
      name: "Demo Organization",
      tier: "standard",
      primary_contact_name: "Demo Contact",
      primary_contact_email: "demo@sentinel.local",
      primary_contact_phone: "+27 11 000 0000",
    },
    contract: base?.contract || {
      type: "comprehensive",
      status: "active",
      start_date: `${year}-01-01`,
      end_date: `${year}-12-31`,
      auto_renew: true,
      monthly_fee_zar: 120000,
      pricing_basis: "fixed_monthly",
      payment_terms: "30 days",
      billing_cycle_days: 30,
    },
    sla_terms: base?.sla_terms || [],
    budget: base?.budget || {
      year,
      monthly_total_zar: 0,
      breakdown: {
        labor_zar: 0,
        parts_zar: 0,
        subcontractors_zar: 0,
        overhead_zar: 0,
      },
      risk_buffer_percent: 10,
      equipment_type_budgets: {},
    },
    condition_assessment: base?.condition_assessment || {
      date: `${year}-01-01`,
      assessor: "Unknown",
      overall_score: 3,
      mechanical_score: 3,
      electrical_score: 3,
      structural_score: 3,
      notes: "No assessment data available.",
      risk_factors: [],
    },
    profitability_snapshot: base?.profitability_snapshot || {
      ytd_revenue_zar: base?.contract?.monthly_fee_zar || 0,
      ytd_direct_costs_zar: 0,
      ytd_overhead_zar: 0,
      ytd_penalties_zar: 0,
      gross_margin_percent: 0,
      net_margin_percent: 0,
    },
  };
}

function normalizeContractFromApi(payload: any): Contract {
  const contract = payload?.contract || payload;
  const org = contract?.organizations || payload?.organizations || {};
  const budgetSummary = payload?.budget_summary || {};
  const now = new Date();
  const year = now.getFullYear();

  return buildFallbackContract({
    id: contract?.id,
    contract_code: contract?.code || payload?.code,
    organization: {
      code: org?.code || "ORG-UNKNOWN",
      name: org?.name || "Unknown Organization",
      tier: org?.tier || "standard",
      primary_contact_name: org?.primary_contact_name || "Unknown",
      primary_contact_email: org?.primary_contact_email || "unknown@sentinel.local",
      primary_contact_phone: org?.primary_contact_phone || "+27 11 000 0000",
    },
    contract: {
      type: contract?.contract_type || contract?.type || "comprehensive",
      status: contract?.status || "active",
      start_date: contract?.start_date || `${year}-01-01`,
      end_date: contract?.end_date || `${year}-12-31`,
      auto_renew: contract?.auto_renew ?? true,
      monthly_fee_zar: Number(contract?.monthly_fee_zar || 0),
      pricing_basis: contract?.pricing_basis || "fixed_monthly",
      payment_terms: contract?.payment_terms || "30 days",
      billing_cycle_days: contract?.billing_cycle_days || 30,
    },
    sla_terms: payload?.sla_terms || [],
    budget: {
      year: budgetSummary?.year || year,
      monthly_total_zar: budgetSummary?.total_budget_zar
        ? Number(budgetSummary.total_budget_zar) / 12
        : 0,
      breakdown: {
        labor_zar: 0,
        parts_zar: 0,
        subcontractors_zar: 0,
        overhead_zar: 0,
      },
      risk_buffer_percent: 10,
      equipment_type_budgets: {},
    },
    profitability_snapshot: {
      ytd_revenue_zar: Number(contract?.monthly_fee_zar || 0),
      ytd_direct_costs_zar: 0,
      ytd_overhead_zar: 0,
      ytd_penalties_zar: 0,
      gross_margin_percent: 0,
      net_margin_percent: 0,
    },
  });
}

export interface SLATerm {
  metric_type: string;
  target_value: number;
  measurement_period_days: number;
  penalty_per_breach_zar: number;
  penalty_cap_monthly_zar: number;
  exclusions: string[];
  current_value?: number;
  status?: "met" | "at_risk" | "breached";
}

export interface Budget {
  year: number;
  monthly_total_zar: number;
  breakdown: {
    labor_zar: number;
    parts_zar: number;
    subcontractors_zar: number;
    overhead_zar: number;
  };
  risk_buffer_percent: number;
  equipment_type_budgets: Record<string, number>;
}

export interface BudgetReport {
  contract_id: string;
  year: number;
  totals: {
    total_budget_zar: number;
    total_actual_zar: number;
    variance_zar: number;
    spend_percentage: number;
  };
  monthly: {
    month: number;
    total_budget_zar: number;
    total_actual_zar: number;
    variance_zar: number;
    spend_percentage: number;
  }[];
  equipment_type_breakdown: {
    equipment_type: string;
    total_budget_zar: number;
    total_actual_zar: number;
    variance_zar: number;
    spend_percentage: number;
  }[];
  alert_summary?: Record<string, number>;
}

export interface BudgetAlert {
  id?: string;
  period_year: number;
  period_month: number;
  severity: "warning" | "critical";
  message?: string;
  status?: "open" | "acknowledged" | "resolved";
  equipment_type?: string | null;
  spend_percentage?: number;
}

function mapVarianceFromReport(report: BudgetReport): BudgetVariance[] {
  if (report.equipment_type_breakdown && report.equipment_type_breakdown.length > 0) {
    return report.equipment_type_breakdown.map((row) => ({
      category: row.equipment_type,
      budgeted_zar: row.total_budget_zar,
      actual_zar: row.total_actual_zar,
      variance_zar: row.variance_zar,
      variance_percent: row.spend_percentage,
    }));
  }

  return [
    {
      category: "Total",
      budgeted_zar: report.totals.total_budget_zar,
      actual_zar: report.totals.total_actual_zar,
      variance_zar: report.totals.variance_zar,
      variance_percent: report.totals.spend_percentage,
    },
  ];
}

export interface BudgetVariance {
  category: string;
  budgeted_zar: number;
  actual_zar: number;
  variance_zar: number;
  variance_percent: number;
}

export interface ConditionAssessment {
  date: string;
  assessor: string;
  overall_score: number;
  mechanical_score: number;
  electrical_score: number;
  structural_score: number;
  notes: string;
  risk_factors: string[];
}

export interface ProfitabilitySnapshot {
  ytd_revenue_zar: number;
  ytd_direct_costs_zar: number;
  ytd_overhead_zar: number;
  ytd_penalties_zar: number;
  gross_margin_percent: number;
  net_margin_percent: number;
}

export interface ContractSummary {
  total_contracts: number;
  active_contracts: number;
  monthly_revenue_zar: number;
  average_margin_percent: number;
  expiring_soon: number;
  at_risk: number;
}

// ============= API Functions =============

export const contractApi = {
  // Organizations
  getOrganizations: (tier?: string): Promise<Organization[]> => {
    const params = tier ? `?tier=${encodeURIComponent(tier)}` : "";
    return fetchJson(`/api/contracts/organizations${params}`);
  },

  createOrganization: (data: Partial<Organization>): Promise<Organization> => {
    return postJson("/api/contracts/organizations", data);
  },

  // Contracts
  getContracts: (params?: {
    building_id?: string;
    status?: string;
  }): Promise<Contract[]> => {
    const searchParams = new URLSearchParams();
    if (params?.building_id) searchParams.set("building_id", params.building_id);
    if (params?.status) searchParams.set("status", params.status);
    const qs = searchParams.toString();
    return fetchJson<{ contracts: any[] }>(`/api/contracts${qs ? `?${qs}` : ""}`)
      .then(async (payload) => {
        const contracts = payload?.contracts || [];
        if (contracts.length === 0) {
          return [];
        }
        const detailed = await Promise.all(
          contracts.map(async (c) => {
            try {
              const detail = await fetchJson<any>(
                `/api/contracts/${encodeURIComponent(c.id)}`
              );
              return normalizeContractFromApi(detail);
            } catch {
              return normalizeContractFromApi(c);
            }
          })
        );
        return detailed;
      });
  },

  getContract: (id: string): Promise<Contract> => {
    return fetchJson(`/api/contracts/${encodeURIComponent(id)}`).then((payload) =>
      normalizeContractFromApi(payload)
    );
  },

  getContractSummary: (buildingId?: string): Promise<ContractSummary> => {
    const params = buildingId
      ? `?building_id=${encodeURIComponent(buildingId)}`
      : "";
    return fetchJson(`/api/contracts/summary${params}`);
  },

  createContract: (data: unknown): Promise<Contract> => {
    return postJson("/api/contracts", data);
  },

  updateContractStatus: (
    id: string,
    status: string
  ): Promise<{ success: boolean }> => {
    return patchJson(`/api/contracts/${encodeURIComponent(id)}/status`, {
      status,
    });
  },

  // SLA Terms
  getSLATerms: (contractId: string): Promise<SLATerm[]> => {
    return fetchJson(
      `/api/contracts/${encodeURIComponent(contractId)}/sla-terms`
    );
  },

  addSLATerm: (contractId: string, data: Partial<SLATerm>): Promise<SLATerm> => {
    return postJson(
      `/api/contracts/${encodeURIComponent(contractId)}/sla-terms`,
      data
    );
  },

  // Equipment
  getContractEquipment: (
    contractId: string
  ): Promise<{ equipment_id: string; name: string; type: string }[]> => {
    return fetchJson(
      `/api/contracts/${encodeURIComponent(contractId)}/equipment`
    );
  },

  assignEquipment: (
    contractId: string,
    data: { equipment_ids: string[] }
  ): Promise<{ success: boolean }> => {
    return postJson(
      `/api/contracts/${encodeURIComponent(contractId)}/equipment`,
      data
    );
  },

  // Budgets
  getBudgets: (contractId: string, year?: number): Promise<Budget[]> => {
    const params = year ? `?year=${year}` : "";
    return fetchJson(
      `/api/contracts/${encodeURIComponent(contractId)}/budgets${params}`
    );
  },

  getBudgetVariance: (
    contractId: string,
    year: number
  ): Promise<BudgetVariance[]> => {
    return fetchJson<BudgetReport>(
      `/api/contracts/${encodeURIComponent(contractId)}/budgets/report?year=${year}`
    ).then((report) => mapVarianceFromReport(report));
  },

  getBudgetReport: (contractId: string, year: number): Promise<BudgetReport> => {
    return fetchJson(
      `/api/contracts/${encodeURIComponent(contractId)}/budgets/report?year=${year}`
    );
  },

  exportBudgetReport: async (
    contractId: string,
    year: number,
    format: "csv" | "pdf",
    month?: number
  ): Promise<Blob> => {
    const baseUrl = resolveApiBaseUrl();
    const params = new URLSearchParams();
    params.set("year", `${year}`);
    params.set("format", format);
    if (month) params.set("month", `${month}`);
    const res = await fetch(
      `${baseUrl}/api/contracts/${encodeURIComponent(contractId)}/budgets/report/export?${params.toString()}`,
      { headers: authHeaders() }
    );
    if (!res.ok) {
      throw new Error(`Export failed: ${res.statusText}`);
    }
    return res.blob();
  },

  getBudgetReportByMonth: (
    contractId: string,
    year: number,
    month?: number
  ): Promise<BudgetReport> => {
    const params = new URLSearchParams();
    params.set("year", `${year}`);
    if (month) params.set("month", `${month}`);
    return fetchJson(
      `/api/contracts/${encodeURIComponent(contractId)}/budgets/report?${params.toString()}`
    );
  },

  getBudgetAlerts: (
    contractId: string,
    year?: number
  ): Promise<BudgetAlert[]> => {
    const params = new URLSearchParams();
    if (year) params.set("year", `${year}`);
    const qs = params.toString();
    return fetchJson<{ alerts: BudgetAlert[] }>(
      `/api/contracts/${encodeURIComponent(contractId)}/budget-variance/alerts${qs ? `?${qs}` : ""}`
    ).then((payload) => payload.alerts || []);
  },

  updateBudgetAlertStatus: (
    alertId: string,
    status: "open" | "acknowledged" | "resolved"
  ): Promise<BudgetAlert> => {
    return patchJson(
      `/api/contracts/budget-variance/alerts/${encodeURIComponent(alertId)}?status=${status}`
    );
  },

  // Assessments
  getAssessments: (
    buildingId?: string
  ): Promise<ConditionAssessment[]> => {
    const params = buildingId
      ? `?building_id=${encodeURIComponent(buildingId)}`
      : "";
    return fetchJson(`/api/contracts/assessments${params}`);
  },

  getEquipmentAssessment: (
    equipmentId: string
  ): Promise<ConditionAssessment> => {
    return fetchJson(
      `/api/contracts/assessments/equipment/${encodeURIComponent(equipmentId)}`
    );
  },
};
