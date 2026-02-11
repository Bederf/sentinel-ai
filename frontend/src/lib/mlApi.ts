/**
 * ML API Client - Machine Learning predictions and anomaly detection
 * Phase 43: ML Model Development
 */

import { authorizedFetch } from "./api/client";

const API_BASE_URL = import.meta.env.VITE_API_URL || "";

// ============= Response Interfaces =============

export interface LSTMPrediction {
  equipment_id: string;
  equipment_type: string;
  predictions: {
    "24h": number | null;
    "48h": number | null;
    "72h": number | null;
  };
  confidence: number;
  timestamp: string;
  model_info?: {
    model_id: string;
  };
  error?: string;
}

export interface TrendData {
  equipment_id: string;
  equipment_type: string;
  historical: number[];
  predicted: {
    "24h": number | null;
    "48h": number | null;
    "72h": number | null;
  };
  visualization_data: {
    x_historical: number[];
    y_historical: number[];
    x_predicted: number[];
    y_predicted: (number | null)[];
  };
  timestamp: string;
}

export interface AnomalyResult {
  equipment_id: string;
  equipment_type?: string;
  is_anomaly: boolean | null;
  anomaly_score: number | null;
  threshold: number | null;
  score_pct: number | null;
  severity: "normal" | "warning" | "elevated" | "high" | "critical" | null;
  timestamp?: string;
  model_info?: {
    model_id: string;
  };
  error?: string;
}

export interface AnomalyHistoryEntry {
  date: string;
  score: number;
  threshold: number;
  is_anomaly: boolean;
}

export interface MLModel {
  model_id: string;
  model_type: "lstm" | "autoencoder";
  equipment_type: string;
  status: "active" | "inactive" | "registered";
  registered_at: string;
  metrics: Record<string, number>;
}

export interface MLHealth {
  status: string;
  total_models: number;
  active_models: number;
  lstm_models_active: number;
  autoencoder_models_active: number;
  equipment_types_covered: string[];
}

export interface TrainResponse {
  status: string;
  message: string;
  model_id?: string;
  metrics?: Record<string, number>;
}

// ============= API Functions =============

/**
 * Get LSTM prediction for equipment
 */
export async function getLSTMPrediction(
  equipmentId: string,
  equipmentType: string
): Promise<LSTMPrediction> {
  const response = await authorizedFetch(`/api/ml/predictions/lstm/${equipmentId}?equipment_type=${equipmentType}`
  );
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to get prediction");
  }
  return response.json();
}

/**
 * Get trend data for visualization
 */
export async function getPredictionTrend(
  equipmentId: string,
  equipmentType: string,
  hoursHistory: number = 168
): Promise<TrendData> {
  const response = await authorizedFetch(`/api/ml/predictions/trend/${equipmentId}?equipment_type=${equipmentType}&hours_history=${hoursHistory}`
  );
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to get trend data");
  }
  return response.json();
}

/**
 * Get batch predictions for multiple equipment
 */
export async function getBatchPredictions(
  equipmentList: Array<{ equipment_id: string; equipment_type: string }>
): Promise<LSTMPrediction[]> {
  const response = await authorizedFetch(`/api/ml/predictions/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(equipmentList),
  });
  if (!response.ok) {
    throw new Error("Failed to get batch predictions");
  }
  return response.json();
}

/**
 * Check equipment for anomalies
 */
export async function checkEquipmentAnomaly(
  equipmentId: string,
  equipmentType: string
): Promise<AnomalyResult> {
  const response = await authorizedFetch(`/api/ml/anomalies/equipment/${equipmentId}?equipment_type=${equipmentType}`
  );
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to check anomaly");
  }
  return response.json();
}

/**
 * Get anomaly status for all equipment
 */
export async function getAllAnomalies(limit: number = 20): Promise<AnomalyResult[]> {
  const response = await authorizedFetch(`/api/ml/anomalies/all?limit=${limit}`);
  if (!response.ok) {
    throw new Error("Failed to get anomalies");
  }
  return response.json();
}

/**
 * Get active anomaly alerts
 */
export async function getAnomalyAlerts(): Promise<AnomalyResult[]> {
  const response = await authorizedFetch(`/api/ml/anomalies/alerts`);
  if (!response.ok) {
    throw new Error("Failed to get anomaly alerts");
  }
  return response.json();
}

/**
 * Get anomaly score history
 */
export async function getAnomalyHistory(
  equipmentId: string,
  equipmentType: string,
  days: number = 7
): Promise<AnomalyHistoryEntry[]> {
  const response = await authorizedFetch(`/api/ml/anomalies/history/${equipmentId}?equipment_type=${equipmentType}&days=${days}`
  );
  if (!response.ok) {
    throw new Error("Failed to get anomaly history");
  }
  return response.json();
}

/**
 * List all ML models
 */
export async function listMLModels(
  modelType?: string,
  equipmentType?: string,
  status?: string
): Promise<MLModel[]> {
  const params = new URLSearchParams();
  if (modelType) params.append("model_type", modelType);
  if (equipmentType) params.append("equipment_type", equipmentType);
  if (status) params.append("status", status);

  const response = await authorizedFetch(`/api/ml/models?${params}`);
  if (!response.ok) {
    throw new Error("Failed to list models");
  }
  return response.json();
}

/**
 * Get ML service health
 */
export async function getMLHealth(): Promise<MLHealth> {
  const response = await authorizedFetch(`/api/ml/health`);
  if (!response.ok) {
    throw new Error("Failed to get ML health");
  }
  return response.json();
}

/**
 * Train a new model
 */
export async function trainModel(
  modelType: "lstm" | "autoencoder",
  equipmentType: string,
  epochs: number = 50,
  useDemoData: boolean = true
): Promise<TrainResponse> {
  const response = await authorizedFetch(`/api/ml/train/${modelType}/${equipmentType}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ epochs, use_demo_data: useDemoData }),
    }
  );
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Training failed");
  }
  return response.json();
}

/**
 * Activate a specific model version
 */
export async function activateModel(modelId: string): Promise<{ status: string; message: string }> {
  const response = await authorizedFetch(`/api/ml/models/${modelId}/activate`, {
    method: "POST",
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to activate model");
  }
  return response.json();
}

// ============= Utility Functions =============

/**
 * Get severity color for UI
 */
export function getSeverityColor(severity: AnomalyResult["severity"]): string {
  switch (severity) {
    case "normal":
      return "green";
    case "warning":
      return "yellow";
    case "elevated":
      return "orange";
    case "high":
      return "red";
    case "critical":
      return "red";
    default:
      return "gray";
  }
}

/**
 * Get severity badge text
 */
export function getSeverityBadge(severity: AnomalyResult["severity"]): string {
  switch (severity) {
    case "normal":
      return "Normal";
    case "warning":
      return "Warning";
    case "elevated":
      return "Elevated";
    case "high":
      return "High";
    case "critical":
      return "Critical";
    default:
      return "Unknown";
  }
}

/**
 * Format prediction value with unit
 */
export function formatPrediction(value: number | null, unit: string = "°C"): string {
  if (value === null) return "N/A";
  return `${value.toFixed(1)}${unit}`;
}
