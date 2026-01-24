/**
 * API Client for BMS Intelligence Backend
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:9095";

// ============= Response Interfaces =============

interface HealthResponse {
  status: string;
  version: string;
}

interface ApiError {
  message: string;
  status: number;
}

// Site/Building interface
export interface Site {
  id: string;
  name: string;
  location: string;
  region: string;
  type: string;
  equipment_count: number;
  alert_count: number;
  status: "normal" | "warning" | "critical";
}

// Equipment interface
export interface Equipment {
  id: string;
  name: string;
  type: string;
  site_id: string;
  site_name: string;
  status: "online" | "offline" | "maintenance";
  last_reading?: {
    timestamp: string;
    value: number;
    unit: string;
  };
}

// Alert interface
export interface Alert {
  id: string;
  site_id: string;
  site_name: string;
  equipment_id: string;
  equipment_name: string;
  severity: "low" | "medium" | "high" | "critical";
  message: string;
  timestamp: string;
  acknowledged: boolean;
}

// Anomaly prediction interface
export interface Anomaly {
  id: string;
  site_id: string;
  site_name: string;
  equipment_id: string;
  equipment_name: string;
  prediction: string;
  confidence: number;
  predicted_date: string;
  recommendation: string;
}

// Dashboard stats interface
export interface DashboardStats {
  total_sites: number;
  total_equipment: number;
  total_sensors: number;
  active_alerts: number;
  critical_alerts: number;
  pending_anomalies: number;
  uptime_percent: number;
}

// Energy data point interface
export interface EnergyDataPoint {
  date: string;
  site_id: string;
  site_name: string;
  hvac_kwh: number;
  lighting_kwh: number;
  other_kwh: number;
  total_kwh: number;
}

// Energy response interface
export interface EnergyResponse {
  days: number;
  site_id: string | null;
  data: EnergyDataPoint[];
}

// Prediction interface
export interface Prediction {
  id: string;
  equipment_id: string;
  site_id: string;
  site_name: string;
  equipment_name: string;
  equipment_type: string;
  prediction_type: string;
  probability_percent: number;
  confidence: "high" | "medium" | "low";
  predicted_failure_date: string;
  timeframe_days: number;
  severity: "critical" | "high" | "medium" | "low";
  evidence: {
    repeat_work_orders: number;
    repeat_period_months: number;
    alarm_frequency: Record<string, number>;
    asset_age_years: number;
    expected_life_years: number;
    technician_notes: string[];
    latest_reading: {
      parameter: string;
      value: number;
      baseline: number;
      threshold: number;
      trend: string;
    };
  };
  contributing_factors: Array<{
    factor: string;
    weight: number;
    description: string;
  }>;
  similar_failures: Array<{
    site: string;
    equipment: string;
    failure_date: string;
    common_factors: string[];
  }>;
  financial_impact: {
    repair_cost_zar: number;
    replacement_cost_zar: number;
    downtime_cost_per_hour_zar: number;
    estimated_repair_hours: number;
    potential_loss_zar: number;
  };
  recommended_action: string;
  parts_required: string[];
  urgency: string;
}

// Predictions response interface
export interface PredictionsResponse {
  total: number;
  avg_probability: number;
  total_repair_cost_zar: number;
  total_potential_loss_zar: number;
  potential_savings_zar: number;
  by_severity: Record<string, number>;
  by_equipment_type: Record<string, number>;
  predictions: Prediction[];
}

/**
 * Generic fetch wrapper with error handling
 */
async function fetchApi<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;

  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error: ApiError = {
      message: `API Error: ${response.statusText}`,
      status: response.status,
    };
    throw error;
  }

  return response.json();
}

/**
 * Stream chat response using Server-Sent Events
 *
 * @param message - User message to send
 * @param conversationId - Optional conversation ID for context
 * @param onChunk - Callback called for each text chunk received
 */
export async function streamChat(
  message: string,
  conversationId: string | undefined,
  onChunk: (chunk: string) => void
): Promise<void> {
  const url = `${API_BASE_URL}/api/chat`;

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
    }),
  });

  if (!response.ok) {
    throw new Error(`Chat API error: ${response.status} ${response.statusText}`);
  }

  if (!response.body) {
    throw new Error("No response body available for streaming");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      // Decode the chunk
      const text = decoder.decode(value, { stream: true });

      // Parse SSE format: "data: <content>\n\n"
      const lines = text.split("\n");
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6); // Remove "data: " prefix

          // Check for completion sentinel
          if (data === "[DONE]") {
            return;
          }

          // Call callback with the chunk
          onChunk(data);
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * API Methods
 */
export const api = {
  /**
   * Check backend health status
   */
  async health(): Promise<HealthResponse> {
    return fetchApi<HealthResponse>("/api/health");
  },

  /**
   * Stream chat with AI assistant
   */
  streamChat,

  // ============= Dashboard API Methods =============

  /**
   * Get all sites/buildings
   */
  async getSites(): Promise<Site[]> {
    return fetchApi<Site[]>("/api/sites");
  },

  /**
   * Get dashboard statistics overview
   */
  async getStats(): Promise<DashboardStats> {
    return fetchApi<DashboardStats>("/api/stats");
  },

  /**
   * Get active alerts
   */
  async getAlerts(): Promise<Alert[]> {
    return fetchApi<Alert[]>("/api/alerts");
  },

  /**
   * Get anomaly predictions
   */
  async getAnomalies(): Promise<Anomaly[]> {
    return fetchApi<Anomaly[]>("/api/anomalies");
  },

  /**
   * Get equipment list
   */
  async getEquipment(): Promise<Equipment[]> {
    return fetchApi<Equipment[]>("/api/equipment");
  },

  /**
   * Get energy consumption data
   * @param siteId - Optional site ID filter
   * @param days - Number of days (default 30)
   */
  async getEnergy(
    siteId: string | null = null,
    days: number = 30
  ): Promise<EnergyResponse> {
    const params = new URLSearchParams();
    if (siteId) {
      params.append("site_id", siteId);
    }
    params.append("days", days.toString());
    return fetchApi<EnergyResponse>(`/api/energy?${params.toString()}`);
  },

  /**
   * Get AI-driven failure predictions
   * @param siteId - Optional site ID filter
   * @param equipmentType - Optional equipment type filter
   * @param severity - Optional severity filter
   * @param minProbability - Optional minimum probability filter
   */
  async getPredictions(
    siteId?: string,
    equipmentType?: string,
    severity?: string,
    minProbability?: number
  ): Promise<PredictionsResponse> {
    const params = new URLSearchParams();
    if (siteId) {
      params.append("site_id", siteId);
    }
    if (equipmentType) {
      params.append("equipment_type", equipmentType);
    }
    if (severity) {
      params.append("severity", severity);
    }
    if (minProbability !== undefined) {
      params.append("min_probability", minProbability.toString());
    }
    const queryString = params.toString();
    return fetchApi<PredictionsResponse>(
      `/api/predictions${queryString ? `?${queryString}` : ""}`
    );
  },

  /**
   * Get single prediction detail by ID
   * @param predictionId - Prediction ID
   */
  async getPrediction(predictionId: string): Promise<Prediction> {
    return fetchApi<Prediction>(`/api/predictions/${predictionId}`);
  },
};

export default api;
