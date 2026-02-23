/**
 * Energy Flow Diagram
 *
 * Simplified Sankey-style energy flow showing:
 * - 4 nodes: Solar, BESS, Building, Grid
 * - Animated flow arrows with kW values
 * - Direction indicates import vs export
 * - BESS shows charging/discharging direction
 * - CSS-based with SVG arrows (no heavy charting library)
 */

import { useState, useEffect, useCallback } from "react";
import { Sun, Battery, Building2, Plug } from "lucide-react";
import type { SolarOverview } from "../../lib/solarApi";
import { fetchSolarOverview } from "../../lib/solarApi";
import { isExpectedApiError } from "../../lib/api";
import { useSimulation } from "../../contexts/SimulationContext";

interface EnergyFlowDiagramProps {
  siteId: string;
}

interface FlowPath {
  from: string;
  to: string;
  power_kw: number;
  active: boolean;
  color: string;
  label: string;
}

export function EnergyFlowDiagram({ siteId }: EnergyFlowDiagramProps) {
  const [overview, setOverview] = useState<SolarOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const { running, solarEfficiency, simulatedHour } = useSimulation();

  const loadData = useCallback(async () => {
    try {
      const data = await fetchSolarOverview(siteId);
      setOverview(data);
    } catch (err) {
      if (!isExpectedApiError(err)) {
        console.error("Failed to load solar overview for flow diagram:", err);
      }
      // Fallback: set Sandton specs so simulation can drive values
      setOverview({
        site_id: siteId,
        site_name: "Solar Campus",
        installed_capacity_kwp: 3900,
        current_generation_kw: 0,
        daily_yield_kwh: 0,
        expected_daily_yield_kwh: 20000,
        performance_ratio: 0.92,
        bess_soc_percent: 65,
        bess_mode: "charging",
        grid_import_kw: 0,
        grid_export_kw: 0,
        self_consumption_percent: 78,
        estimated_savings_today_zar: 0,
        plants: []
      });
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 15000);
    return () => clearInterval(interval);
  }, [loadData]);

  if (loading) {
    return (
      <div
        className="rounded-md p-6"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="animate-pulse h-48 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }} />
      </div>
    );
  }

  if (!overview) {
    return (
      <div
        className="rounded-md p-6 text-center"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          No energy flow data
        </span>
      </div>
    );
  }

  const safeNumber = (value: number | null | undefined) => (
    typeof value === "number" && Number.isFinite(value) ? value : 0
  );

  const installedCapacity = overview.installed_capacity_kwp || 3900;
  let currentGenerationKw = safeNumber(overview.current_generation_kw);
  let gridExportKw = safeNumber(overview.grid_export_kw);
  let gridImportKw = safeNumber(overview.grid_import_kw);
  let bessSocPercent = safeNumber(overview.bess_soc_percent);
  let bessMode = overview.bess_mode || "idle";

  // When simulation is running, compute flows from simulation context
  // BESS mode follows TOU dispatch (aligned with backend _bess_mode_for_hour):
  //   Peak (06-09, 17-19): discharge
  //   Standard (09-17, 19-22): idle (solar tops up if excess)
  //   Off-peak (22-06): grid charge
  if (running && solarEfficiency !== undefined) {
    currentGenerationKw = Math.round((solarEfficiency / 100) * installedCapacity);
    const buildingLoad = (simulatedHour >= 7 && simulatedHour <= 18) ? 1200 : 400;

    // TOU-based BESS mode (matches backend solar_connector_huawei._bess_mode_for_hour)
    const isPeak = (simulatedHour >= 6 && simulatedHour < 9) || (simulatedHour >= 17 && simulatedHour < 19);
    const isOffPeak = simulatedHour >= 22 || simulatedHour < 6;

    if (isPeak && bessSocPercent > 20) {
      bessMode = "discharging";
    } else if (isOffPeak) {
      bessMode = "charging";
    } else {
      // Standard hours: idle, but solar tops up if excess
      bessMode = (currentGenerationKw > buildingLoad) ? "charging" : "idle";
    }

    if (currentGenerationKw > buildingLoad) {
      const excess = currentGenerationKw - buildingLoad;
      const bessCharge = bessMode === "charging" ? Math.min(excess * 0.6, 500) : 0;
      gridExportKw = Math.round(excess - bessCharge);
      gridImportKw = 0;
      bessSocPercent = Math.min(95, 40 + simulatedHour * 3);
    } else {
      gridImportKw = Math.round(buildingLoad - currentGenerationKw);
      gridExportKw = 0;
      if (bessMode === "discharging") {
        bessSocPercent = Math.max(20, 80 - (simulatedHour - 6) * 5);
      } else {
        bessSocPercent = simulatedHour < 6 ? 35 : Math.min(90, 40 + simulatedHour * 3);
      }
    }
  }

  // Compute flows
  const solarToBuilding = Math.max(0, currentGenerationKw - gridExportKw);
  const solarToBess = bessMode === "charging"
    ? Math.min(currentGenerationKw * 0.3, currentGenerationKw)
    : 0;
  const solarToGrid = gridExportKw;
  const gridToBuilding = gridImportKw;
  const bessToBuilding = bessMode === "discharging"
    ? Math.max(0, currentGenerationKw * 0.2)
    : 0;

  const flows: FlowPath[] = [
    {
      from: "solar",
      to: "building",
      power_kw: Math.max(0, solarToBuilding - solarToBess),
      active: solarToBuilding > 0,
      color: "#FACC15",
      label: "Solar to Building",
    },
    {
      from: "solar",
      to: "bess",
      power_kw: solarToBess,
      active: solarToBess > 0,
      color: "#3B82F6",
      label: "Solar to BESS",
    },
    {
      from: "solar",
      to: "grid",
      power_kw: solarToGrid,
      active: solarToGrid > 0,
      color: "#10B981",
      label: "Export to Grid",
    },
    {
      from: "grid",
      to: "building",
      power_kw: gridToBuilding,
      active: gridToBuilding > 0,
      color: "#EF4444",
      label: "Grid Import",
    },
    {
      from: "bess",
      to: "building",
      power_kw: bessToBuilding,
      active: bessToBuilding > 0,
      color: "#8B5CF6",
      label: "BESS Discharge",
    },
  ];

  return (
    <div
      className="rounded-md overflow-hidden"
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
      {/* Panel Header */}
      <div
        className="p-4 flex items-center justify-between"
        style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
      >
        <div className="flex items-center gap-3">
          <div className="p-2 rounded" style={{ background: "rgba(250, 204, 21, 0.15)" }}>
            <Plug className="h-5 w-5" style={{ color: "#FACC15" }} />
          </div>
          <div>
            <h3 className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
              Energy Flow
            </h3>
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Real-time power distribution
            </span>
          </div>
        </div>
      </div>

      {/* Flow Diagram — viewBox 0 0 600 220; nodes aligned to line endpoints */}
      <div className="p-6">
        <div
          className="relative w-full"
          style={{ aspectRatio: "600/220", minHeight: "200px" }}
        >
          {/* SVG for flow paths */}
          <svg
            className="absolute inset-0 w-full h-full"
            viewBox="0 0 600 220"
            preserveAspectRatio="xMidYMid meet"
          >
            {/* Animated flow definitions */}
            <defs>
              {flows.filter(f => f.active).map((flow, idx) => (
                <linearGradient key={`grad-${idx}`} id={`flow-grad-${idx}`} x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" style={{ stopColor: flow.color, stopOpacity: 0.8 }} />
                  <stop offset="100%" style={{ stopColor: flow.color, stopOpacity: 0.3 }} />
                </linearGradient>
              ))}
            </defs>

            {/* Solar (left) -> Building (center) */}
            {flows[0].active && (
              <g>
                <line
                  x1="130" y1="60" x2="260" y2="110"
                  stroke={flows[0].color}
                  strokeWidth={Math.max(2, Math.min(6, flows[0].power_kw / 200))}
                  strokeDasharray="8 4"
                  opacity="0.7"
                >
                  <animate attributeName="stroke-dashoffset" from="24" to="0" dur="1.5s" repeatCount="indefinite" />
                </line>
                <text x="180" y="75" fill={flows[0].color} fontSize="10" fontWeight="bold">
                  {flows[0].power_kw.toFixed(0)} kW
                </text>
              </g>
            )}

            {/* Solar (left) -> BESS (bottom-left) */}
            {flows[1].active && (
              <g>
                <line
                  x1="90" y1="90" x2="90" y2="187"
                  stroke={flows[1].color}
                  strokeWidth={Math.max(2, Math.min(6, flows[1].power_kw / 200))}
                  strokeDasharray="8 4"
                  opacity="0.7"
                >
                  <animate attributeName="stroke-dashoffset" from="24" to="0" dur="1.5s" repeatCount="indefinite" />
                </line>
                <text x="100" y="138" fill={flows[1].color} fontSize="10" fontWeight="bold">
                  {flows[1].power_kw.toFixed(0)} kW
                </text>
              </g>
            )}

            {/* Solar (left) -> Grid (right) via export */}
            {flows[2].active && (
              <g>
                <line
                  x1="130" y1="50" x2="470" y2="50"
                  stroke={flows[2].color}
                  strokeWidth={Math.max(2, Math.min(6, flows[2].power_kw / 200))}
                  strokeDasharray="8 4"
                  opacity="0.7"
                >
                  <animate attributeName="stroke-dashoffset" from="24" to="0" dur="1.5s" repeatCount="indefinite" />
                </line>
                <text x="280" y="42" fill={flows[2].color} fontSize="10" fontWeight="bold">
                  Export {flows[2].power_kw.toFixed(0)} kW
                </text>
              </g>
            )}

            {/* Grid (right) -> Building (center) */}
            {flows[3].active && (
              <g>
                <line
                  x1="470" y1="110" x2="340" y2="110"
                  stroke={flows[3].color}
                  strokeWidth={Math.max(2, Math.min(6, flows[3].power_kw / 200))}
                  strokeDasharray="8 4"
                  opacity="0.7"
                >
                  <animate attributeName="stroke-dashoffset" from="24" to="0" dur="1.5s" repeatCount="indefinite" />
                </line>
                <text x="380" y="100" fill={flows[3].color} fontSize="10" fontWeight="bold">
                  {flows[3].power_kw.toFixed(0)} kW
                </text>
              </g>
            )}

            {/* BESS (bottom-left) -> Building (center) */}
            {flows[4].active && (
              <g>
                <line
                  x1="110" y1="187" x2="260" y2="130"
                  stroke={flows[4].color}
                  strokeWidth={Math.max(2, Math.min(6, flows[4].power_kw / 200))}
                  strokeDasharray="8 4"
                  opacity="0.7"
                >
                  <animate attributeName="stroke-dashoffset" from="24" to="0" dur="1.5s" repeatCount="indefinite" />
                </line>
                <text x="180" y="168" fill={flows[4].color} fontSize="10" fontWeight="bold">
                  {flows[4].power_kw.toFixed(0)} kW
                </text>
              </g>
            )}
          </svg>

          {/* Node circles aligned to SVG line endpoints (viewBox 600×220) */}
          <div className="absolute inset-0 z-10 pointer-events-none">
            {/* Solar — left top (110, 55) */}
            <div
              className="absolute flex flex-col items-center"
              style={{
                left: "18.33%",
                top: "25%",
                transform: "translate(-50%, -50%)",
              }}
            >
              <div
                className="w-14 h-14 rounded-full flex items-center justify-center flex-shrink-0"
                style={{ background: "rgba(250, 204, 21, 0.2)", border: "2px solid #FACC15" }}
              >
                <Sun className="h-6 w-6" style={{ color: "#FACC15" }} />
              </div>
              <span className="text-xs font-medium mt-1 whitespace-nowrap" style={{ color: "#FACC15" }}>
                Solar
              </span>
              <span className="text-[10px] whitespace-nowrap" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {currentGenerationKw.toFixed(0)} kW
              </span>
            </div>

            {/* BESS — left bottom (110, 187) */}
            <div
              className="absolute flex flex-col items-center"
              style={{
                left: "18.33%",
                top: "85%",
                transform: "translate(-50%, -50%)",
              }}
            >
              <div
                className="w-14 h-14 rounded-full flex items-center justify-center flex-shrink-0"
                style={{
                  background: bessMode === "charging"
                    ? "rgba(59, 130, 246, 0.2)"
                    : bessMode === "discharging"
                    ? "rgba(139, 92, 246, 0.2)"
                    : "rgba(107, 114, 128, 0.2)",
                  border: `2px solid ${
                    bessMode === "charging"
                      ? "#3B82F6"
                      : bessMode === "discharging"
                      ? "#8B5CF6"
                      : "#6B7280"
                  }`,
                }}
              >
                <Battery
                  className="h-6 w-6"
                  style={{
                    color:
                      bessMode === "charging"
                        ? "#3B82F6"
                        : bessMode === "discharging"
                        ? "#8B5CF6"
                        : "#6B7280",
                  }}
                />
              </div>
              <span className="text-xs font-medium mt-1 whitespace-nowrap" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                BESS
              </span>
              <span className="text-[10px] whitespace-nowrap" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {bessSocPercent.toFixed(0)}% SOC &mdash; {bessMode}
              </span>
            </div>

            {/* Building — center (300, 120) */}
            <div
              className="absolute flex flex-col items-center"
              style={{
                left: "50%",
                top: "54.5%",
                transform: "translate(-50%, -50%)",
              }}
            >
              <div
                className="w-16 h-16 rounded-full flex items-center justify-center flex-shrink-0"
                style={{
                  background: "rgba(59, 130, 246, 0.2)",
                  border: "2px solid var(--color-sentinel-blue)",
                }}
              >
                <Building2 className="h-7 w-7" style={{ color: "var(--color-sentinel-blue)" }} />
              </div>
              <span className="text-xs font-medium mt-1 whitespace-nowrap" style={{ color: "var(--color-sentinel-blue)" }}>
                Building
              </span>
              <span className="text-[10px] whitespace-nowrap" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {(solarToBuilding + gridToBuilding + bessToBuilding).toFixed(0)} kW load
              </span>
            </div>

            {/* Grid — right (470, 80) */}
            <div
              className="absolute flex flex-col items-center"
              style={{
                left: "78.33%",
                top: "36.4%",
                transform: "translate(-50%, -50%)",
              }}
            >
              <div
                className="w-14 h-14 rounded-full flex items-center justify-center flex-shrink-0"
                style={{
                  background: gridExportKw > 0 ? "rgba(16, 185, 129, 0.2)" : "rgba(239, 68, 68, 0.2)",
                  border: `2px solid ${gridExportKw > 0 ? "#10B981" : "#EF4444"}`,
                }}
              >
                <Plug className="h-6 w-6" style={{ color: gridExportKw > 0 ? "#10B981" : "#EF4444" }} />
              </div>
              <span
                className="text-xs font-medium mt-1 whitespace-nowrap"
                style={{ color: gridExportKw > 0 ? "#10B981" : "#EF4444" }}
              >
                Grid
              </span>
              <span className="text-[10px] whitespace-nowrap" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {gridExportKw > 0
                  ? `Export ${gridExportKw.toFixed(0)} kW`
                  : `Import ${gridImportKw.toFixed(0)} kW`}
              </span>
            </div>
          </div>
        </div>

        {/* Flow Legend */}
        <div className="mt-4 flex flex-wrap gap-3 justify-center">
          {flows.filter(f => f.active).map((flow, idx) => (
            <div key={idx} className="flex items-center gap-1.5">
              <div className="w-3 h-0.5 rounded" style={{ background: flow.color }} />
              <span className="text-[10px]" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                {flow.label}: {flow.power_kw.toFixed(0)} kW
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default EnergyFlowDiagram;
