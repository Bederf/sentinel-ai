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

async function postJson<T>(endpoint: string, data: unknown): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
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
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
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
    return fetchJson(`/api/contracts${qs ? `?${qs}` : ""}`);
  },

  getContract: (id: string): Promise<Contract> => {
    return fetchJson(`/api/contracts/${encodeURIComponent(id)}`);
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
    return fetchJson(
      `/api/contracts/${encodeURIComponent(contractId)}/budgets/${year}/variance`
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
