import { useEffect, useState } from "react";

import {
  Play,
  CheckCircle,
  Clock,
} from "lucide-react";
import type { MLModel, TrainResponse } from "../../lib/mlApi";
import { listMLModels, trainModel, activateModel } from "../../lib/mlApi";
import { Badge } from "../Badge";

interface MLModelStatusProps {
  onModelTrained?: (result: TrainResponse) => void;
}

export function MLModelStatus({ onModelTrained }: MLModelStatusProps) {
  const [models, setModels] = useState<MLModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [training, setTraining] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectedModelType, setSelectedModelType] = useState<"lstm" | "autoencoder">("lstm");
  const [selectedEquipmentType, setSelectedEquipmentType] = useState("chiller");
  const [epochs, setEpochs] = useState(50);

  const equipmentTypes = ["chiller", "ahu", "generator", "fcu", "ups"];

  const fetchModels = async () => {
    try {
      setError(null);
      const modelList = await listMLModels();
      setModels(modelList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load models");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchModels();
  }, []);

  const handleTrain = async () => {
    setTraining(true);
    setError(null);

    try {
      const result = await trainModel(
        selectedModelType,
        selectedEquipmentType,
        epochs,
        true
      );

      await fetchModels();

      if (onModelTrained) {
        onModelTrained(result);
      }

      alert(`Model trained successfully: ${result.model_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Training failed");
    } finally {
      setTraining(false);
    }
  };

  const handleActivate = async (modelId: string) => {
    try {
      await activateModel(modelId);
      await fetchModels();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to activate model");
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString();
  };

  const formatMetrics = (metrics: Record<string, number>, modelType: string) => {
    if (modelType === "lstm") {
      return `MAE: ${metrics.mae_24h?.toFixed(3) || "N/A"}, R²: ${metrics.r2_24h?.toFixed(3) || "N/A"}`;
    } else {
      return `Threshold: ${metrics.threshold?.toFixed(6) || "N/A"}, F1: ${metrics.f1_score?.toFixed(3) || "N/A"}`;
    }
  };

  const cardStyle: React.CSSProperties = {
    background: "var(--color-sentinel-bg-panel)",
    border: "1px solid var(--color-sentinel-border)",
    borderRadius: 8,
    padding: 16,
  };

  if (loading) {
    return (
      <div style={cardStyle}>
        <h3 className="text-lg font-semibold mb-4" style={{ color: "var(--color-sentinel-text-primary)" }}>ML Model Status</h3>
        <div className="h-48 flex items-center justify-center">
          <p style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading models...</p>
        </div>
      </div>
    );
  }

  const lstmModels = models.filter((m) => m.model_type === "lstm");
  const autoencoderModels = models.filter((m) => m.model_type === "autoencoder");

  const thStyle: React.CSSProperties = {
    color: "var(--color-sentinel-text-secondary)",
    borderBottom: "1px solid var(--color-sentinel-border)",
    padding: "8px 12px",
    textAlign: "left",
    fontSize: 12,
    fontWeight: 500,
    textTransform: "uppercase",
    letterSpacing: "0.05em",
  };

  const tdStyle: React.CSSProperties = {
    color: "var(--color-sentinel-text-primary)",
    borderBottom: "1px solid var(--color-sentinel-border)",
    padding: "8px 12px",
    fontSize: 14,
  };

  return (
    <div className="space-y-6">
      <div style={cardStyle}>
        <h3 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Train New Model</h3>
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 mt-4">
          <div>
            <p className="mb-1 text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Model Type</p>
            <select
              value={selectedModelType}
              onChange={(event) => setSelectedModelType(event.target.value as "lstm" | "autoencoder")}
              className="w-full rounded-md appearance-none cursor-pointer px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-0"
              style={{
                background: "var(--color-grafana-bg-secondary)",
                border: "1px solid var(--color-grafana-border)",
                color: "var(--color-grafana-text-primary)",
                boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
                outline: "none",
              }}
              aria-label="Select model type"
            >
              <option value="lstm">LSTM (Forecasting)</option>
              <option value="autoencoder">Autoencoder (Anomaly)</option>
            </select>
          </div>

          <div>
            <p className="mb-1 text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Equipment Type</p>
            <select
              value={selectedEquipmentType}
              onChange={(event) => setSelectedEquipmentType(event.target.value)}
              className="w-full rounded-md appearance-none cursor-pointer px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-0"
              style={{
                background: "var(--color-grafana-bg-secondary)",
                border: "1px solid var(--color-grafana-border)",
                color: "var(--color-grafana-text-primary)",
                boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
                outline: "none",
              }}
              aria-label="Select equipment type"
            >
              {equipmentTypes.map((eq) => (
                <option key={eq} value={eq}>
                  {eq.charAt(0).toUpperCase() + eq.slice(1)}
                </option>
              ))}
            </select>
          </div>

          <div>
            <p className="mb-1 text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Epochs</p>
            <input
              type="number"
              value={epochs}
              onChange={(e) => setEpochs(parseInt(e.target.value, 10) || 10)}
              min={10}
              max={200}
              step={10}
              className="w-full rounded-md px-3 py-2 text-sm"
              style={{
                background: "var(--color-grafana-bg-secondary)",
                border: "1px solid var(--color-grafana-border)",
                color: "var(--color-grafana-text-primary)",
                boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
                outline: "none",
              }}
            />
          </div>

          <div className="flex items-end">
            <button
              onClick={handleTrain}
              disabled={training}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-md transition-colors disabled:opacity-50"
              style={{
                background: "var(--color-sentinel-blue)",
                border: "1px solid var(--color-sentinel-blue)",
                color: "#fff",
              }}
            >
              {training ? (
                <div className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              {training ? "Training..." : "Train Model"}
            </button>
          </div>
        </div>

        {error && (
          <p className="mt-4 text-sm" style={{ color: "var(--color-sentinel-red)" }}>
            {error}
          </p>
        )}
      </div>

      <div style={cardStyle}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>LSTM Forecasting Models</h3>
          <Badge style={{ background: "rgba(59,130,246,0.15)", color: "var(--color-sentinel-blue)" }}>
            {lstmModels.length} models
          </Badge>
        </div>

        {lstmModels.length === 0 ? (
          <p style={{ color: "var(--color-sentinel-text-secondary)" }}>No LSTM models trained yet. Train one above!</p>
        ) : (
          <table className="w-full mt-4">
            <thead>
              <tr>
                <th style={thStyle}>Model ID</th>
                <th style={thStyle}>Equipment</th>
                <th style={thStyle}>Status</th>
                <th style={thStyle}>Metrics</th>
                <th style={thStyle}>Trained</th>
                <th style={thStyle}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {lstmModels.map((model) => (
                <tr key={model.model_id}>
                  <td style={tdStyle}>
                    <span className="font-mono text-xs">{model.model_id}</span>
                  </td>
                  <td style={tdStyle}>{model.equipment_type}</td>
                  <td style={tdStyle}>
                    <span
                      className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full"
                      style={{
                        background: model.status === "active" ? "rgba(16,185,129,0.15)" : "rgba(142,142,142,0.15)",
                        color: model.status === "active" ? "var(--color-sentinel-green)" : "var(--color-sentinel-text-secondary)",
                      }}
                    >
                      {model.status === "active" ? <CheckCircle className="h-3 w-3" /> : <Clock className="h-3 w-3" />}
                      {model.status}
                    </span>
                  </td>
                  <td style={tdStyle}>
                    <span className="text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {formatMetrics(model.metrics, "lstm")}
                    </span>
                  </td>
                  <td style={tdStyle}>
                    <span className="text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{formatDate(model.registered_at)}</span>
                  </td>
                  <td style={tdStyle}>
                    {model.status !== "active" && (
                      <button
                        onClick={() => handleActivate(model.model_id)}
                        className="px-2 py-1 text-xs font-medium rounded-md transition-colors"
                        style={{
                          background: "var(--color-sentinel-bg-secondary)",
                          border: "1px solid var(--color-sentinel-border)",
                          color: "var(--color-sentinel-text-primary)",
                        }}
                      >
                        Activate
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div style={cardStyle}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Autoencoder Anomaly Models</h3>
          <Badge style={{ background: "rgba(245,158,11,0.15)", color: "var(--color-sentinel-amber)" }}>
            {autoencoderModels.length} models
          </Badge>
        </div>

        {autoencoderModels.length === 0 ? (
          <p style={{ color: "var(--color-sentinel-text-secondary)" }}>No autoencoder models trained yet. Train one above!</p>
        ) : (
          <table className="w-full mt-4">
            <thead>
              <tr>
                <th style={thStyle}>Model ID</th>
                <th style={thStyle}>Equipment</th>
                <th style={thStyle}>Status</th>
                <th style={thStyle}>Metrics</th>
                <th style={thStyle}>Trained</th>
                <th style={thStyle}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {autoencoderModels.map((model) => (
                <tr key={model.model_id}>
                  <td style={tdStyle}>
                    <span className="font-mono text-xs">{model.model_id}</span>
                  </td>
                  <td style={tdStyle}>{model.equipment_type}</td>
                  <td style={tdStyle}>
                    <span
                      className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full"
                      style={{
                        background: model.status === "active" ? "rgba(16,185,129,0.15)" : "rgba(142,142,142,0.15)",
                        color: model.status === "active" ? "var(--color-sentinel-green)" : "var(--color-sentinel-text-secondary)",
                      }}
                    >
                      {model.status === "active" ? <CheckCircle className="h-3 w-3" /> : <Clock className="h-3 w-3" />}
                      {model.status}
                    </span>
                  </td>
                  <td style={tdStyle}>
                    <span className="text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {formatMetrics(model.metrics, "autoencoder")}
                    </span>
                  </td>
                  <td style={tdStyle}>
                    <span className="text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{formatDate(model.registered_at)}</span>
                  </td>
                  <td style={tdStyle}>
                    {model.status !== "active" && (
                      <button
                        onClick={() => handleActivate(model.model_id)}
                        className="px-2 py-1 text-xs font-medium rounded-md transition-colors"
                        style={{
                          background: "var(--color-sentinel-bg-secondary)",
                          border: "1px solid var(--color-sentinel-border)",
                          color: "var(--color-sentinel-text-primary)",
                        }}
                      >
                        Activate
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default MLModelStatus;
