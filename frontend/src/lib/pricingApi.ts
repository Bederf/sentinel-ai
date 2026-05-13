/**
 * Pricing API Client
 *
 * Supports renewal pricing and benchmarking.
 */

import { getAccessToken } from "./api";
const RAW_API_BASE_URL = import.meta.env.VITE_API_URL || "";

function resolveApiBaseUrl(): string {
  if (!RAW_API_BASE_URL) return "";
  if (window.location.hostname !== "localhost" && RAW_API_BASE_URL.includes("localhost")) {
    return "";
  }
  return RAW_API_BASE_URL;
}

async function fetchJson<T>(endpoint: string): Promise<T> {
  const baseUrl = resolveApiBaseUrl();
  const token = getAccessToken();
  const res = await fetch(`${baseUrl}${endpoint}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
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
  const token = getAccessToken();
  const res = await fetch(`${baseUrl}${endpoint}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
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

export interface RenewalPricingResponse {
  contract_id: string;
  year: number;
  current_monthly_fee_zar: number;
  actual_cost_monthly_avg_zar: number;
  target_margin_pct: number;
  recommended_monthly_fee_zar: number;
  delta_zar: number;
  delta_pct: number;
  notes: string[];
}

export interface PricingBenchmarkResponse {
  contract_id: string;
  similar_contracts: number;
  average_monthly_fee_zar: number;
  min_monthly_fee_zar: number;
  max_monthly_fee_zar: number;
}

export const pricingApi = {
  getRenewalPricing: (
    contractId: string,
    year: number,
    slaTier?: string
  ): Promise<RenewalPricingResponse> => {
    return postJson<RenewalPricingResponse>("/api/pricing/renewal", {
      contract_id: contractId,
      year,
      ...(slaTier ? { sla_tier: slaTier } : {}),
    });
  },

  getBenchmarks: (contractId: string): Promise<PricingBenchmarkResponse> => {
    return fetchJson<PricingBenchmarkResponse>(
      `/api/pricing/benchmarks/${encodeURIComponent(contractId)}`
    );
  },
};
