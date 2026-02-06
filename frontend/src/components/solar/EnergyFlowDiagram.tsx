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

  const loadData = useCallback(async () => {
    try {
      const data = await fetchSolarOverview(siteId);
      setOverview(data);
    } catch (err) {
      console.error("Failed to load solar overview for flow diagram:", err);
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

  // Compute flows
  const solarToBuilding = Math.max(0, overview.current_generation_kw - overview.grid_export_kw);
  const solarToBess = overview.bess_mode === "charging" ? Math.min(overview.current_generation_kw * 0.3, overview.current_generation_kw) : 0;
  const solarToGrid = overview.grid_export_kw;
  const gridToBuilding = overview.grid_import_kw;
  const bessToBuilding = overview.bess_mode === "discharging" ? Math.max(0, overview.current_generation_kw * 0.2) : 0;

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

      {/* Flow Diagram */}
      <div className="p-6">
        <div className="relative" style={{ minHeight: "220px" }}>
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
                  x1="90" y1="90" x2="90" y2="160"
                  stroke={flows[1].color}
                  strokeWidth={Math.max(2, Math.min(6, flows[1].power_kw / 200))}
                  strokeDasharray="8 4"
                  opacity="0.7"
                >
                  <animate attributeName="stroke-dashoffset" from="24" to="0" dur="1.5s" repeatCount="indefinite" />
                </line>
                <text x="100" y="130" fill={flows[1].color} fontSize="10" fontWeight="bold">
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
                  x1="130" y1="180" x2="260" y2="130"
                  stroke={flows[4].color}
                  strokeWidth={Math.max(2, Math.min(6, flows[4].power_kw / 200))}
                  strokeDasharray="8 4"
                  opacity="0.7"
                >
                  <animate attributeName="stroke-dashoffset" from="24" to="0" dur="1.5s" repeatCount="indefinite" />
                </line>
                <text x="180" y="170" fill={flows[4].color} fontSize="10" fontWeight="bold">
                  {flows[4].power_kw.toFixed(0)} kW
                </text>
              </g>
            )}
          </svg>

          {/* Node Icons (positioned absolutely over SVG) */}
          <div className="relative z-10 flex flex-col" style={{ minHeight: "220px" }}>
            {/* Top row: Solar ... Grid */}
            <div className="flex justify-between items-start px-4">
              {/* Solar Node */}
              <div className="flex flex-col items-center">
                <div
                  className="w-16 h-16 rounded-full flex items-center justify-center"
                  style={{ background: "rgba(250, 204, 21, 0.2)", border: "2px solid #FACC15" }}
                >
                  <Sun className="h-7 w-7" style={{ color: "#FACC15" }} />
                </div>
                <span className="text-xs font-medium mt-1" style={{ color: "#FACC15" }}>
                  Solar
                </span>
                <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {overview.current_generation_kw.toFixed(0)} kW
                </span>
              </div>

              {/* Grid Node */}
              <div className="flex flex-col items-center">
                <div
                  className="w-16 h-16 rounded-full flex items-center justify-center"
                  style={{
                    background: overview.grid_export_kw > 0 ? "rgba(16, 185, 129, 0.2)" : "rgba(239, 68, 68, 0.2)",
                    border: `2px solid ${overview.grid_export_kw > 0 ? "#10B981" : "#EF4444"}`,
                  }}
                >
                  <Plug className="h-7 w-7" style={{ color: overview.grid_export_kw > 0 ? "#10B981" : "#EF4444" }} />
                </div>
                <span
                  className="text-xs font-medium mt-1"
                  style={{ color: overview.grid_export_kw > 0 ? "#10B981" : "#EF4444" }}
                >
                  Grid
                </span>
                <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {overview.grid_export_kw > 0
                    ? `Export ${overview.grid_export_kw.toFixed(0)} kW`
                    : `Import ${overview.grid_import_kw.toFixed(0)} kW`}
                </span>
              </div>
            </div>

            {/* Center: Building */}
            <div className="flex justify-center" style={{ marginTop: "-10px" }}>
              <div className="flex flex-col items-center">
                <div
                  className="w-20 h-20 rounded-full flex items-center justify-center"
                  style={{
                    background: "rgba(59, 130, 246, 0.2)",
                    border: "2px solid var(--color-sentinel-blue)",
                  }}
                >
                  <Building2 className="h-8 w-8" style={{ color: "var(--color-sentinel-blue)" }} />
                </div>
                <span className="text-xs font-medium mt-1" style={{ color: "var(--color-sentinel-blue)" }}>
                  Building
                </span>
                <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {(solarToBuilding + gridToBuilding + bessToBuilding).toFixed(0)} kW load
                </span>
              </div>
            </div>

            {/* Bottom-left: BESS */}
            <div className="flex justify-start px-4" style={{ marginTop: "-10px" }}>
              <div className="flex flex-col items-center">
                <div
                  className="w-16 h-16 rounded-full flex items-center justify-center"
                  style={{
                    background: overview.bess_mode === "charging"
                      ? "rgba(59, 130, 246, 0.2)"
                      : overview.bess_mode === "discharging"
                      ? "rgba(139, 92, 246, 0.2)"
                      : "rgba(107, 114, 128, 0.2)",
                    border: `2px solid ${
                      overview.bess_mode === "charging"
                        ? "#3B82F6"
                        : overview.bess_mode === "discharging"
                        ? "#8B5CF6"
                        : "#6B7280"
                    }`,
                  }}
                >
                  <Battery className="h-7 w-7" style={{
                    color: overview.bess_mode === "charging"
                      ? "#3B82F6"
                      : overview.bess_mode === "discharging"
                      ? "#8B5CF6"
                      : "#6B7280",
                  }} />
                </div>
                <span className="text-xs font-medium mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  BESS
                </span>
                <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {overview.bess_soc_percent.toFixed(0)}% SOC &mdash; {overview.bess_mode}
                </span>
              </div>
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
