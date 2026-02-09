/**
 * Inverter Status Matrix
 *
 * Compact traffic-light grid of all inverters:
 * - Grouped by plant (Western Carports / Eastern Carports)
 * - Each tile: name, current kW, status icon (green/yellow/red)
 * - Click tile for detail: efficiency %, temperature, daily yield
 * - Underperforming inverters highlighted with yellow/red border
 * - Fits all 33 inverters at once
 */

import { useState, useEffect, useCallback } from "react";
import { Cpu, X, Thermometer, Zap, Sun, ChevronDown, ChevronUp } from "lucide-react";
import type { SolarInverter, InverterListResponse } from "../../lib/solarApi";
import { fetchInverters } from "../../lib/solarApi";
import { isExpectedApiError } from "../../lib/api";

interface InverterStatusMatrixProps {
  siteId: string;
}

function getStatusColor(status: SolarInverter["status"]): string {
  switch (status) {
    case "normal":
      return "var(--color-sentinel-green)";
    case "warning":
      return "var(--color-sentinel-amber)";
    case "fault":
      return "var(--color-sentinel-red)";
    case "offline":
      return "var(--color-sentinel-text-disabled)";
    default:
      return "var(--color-sentinel-text-secondary)";
  }
}

function getStatusBorder(status: SolarInverter["status"]): string {
  switch (status) {
    case "normal":
      return "1px solid var(--color-sentinel-border)";
    case "warning":
      return "2px solid var(--color-sentinel-amber)";
    case "fault":
      return "2px solid var(--color-sentinel-red)";
    case "offline":
      return "1px solid var(--color-sentinel-text-disabled)";
    default:
      return "1px solid var(--color-sentinel-border)";
  }
}

export function InverterStatusMatrix({ siteId }: InverterStatusMatrixProps) {
  const [data, setData] = useState<InverterListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedInverter, setSelectedInverter] = useState<SolarInverter | null>(null);
  const [collapsedPlants, setCollapsedPlants] = useState<Set<string>>(new Set());

  const loadData = useCallback(async () => {
    try {
      const result = await fetchInverters(siteId);
      setData(result);
      setError(null);
    } catch (err) {
      if (!isExpectedApiError(err)) {
        console.error("Failed to load inverters:", err);
      }
      setError(err instanceof Error ? err.message : "Failed to load");
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
        <div className="animate-pulse space-y-4">
          <div className="h-4 w-40 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }} />
          <div className="grid grid-cols-6 gap-2">
            {[...Array(12)].map((_, i) => (
              <div key={i} className="h-16 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }} />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div
        className="rounded-md p-6 text-center"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <Cpu className="h-8 w-8 mx-auto mb-2" style={{ color: "var(--color-sentinel-text-disabled)" }} />
        <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          {error || "No inverter data available"}
        </span>
      </div>
    );
  }

  // Group inverters by plant
  const plantGroups = data.inverters.reduce<Record<string, SolarInverter[]>>((groups, inv) => {
    const plant = inv.plant_name || "Unknown Plant";
    if (!groups[plant]) groups[plant] = [];
    groups[plant].push(inv);
    return groups;
  }, {});

  const togglePlant = (plantName: string) => {
    setCollapsedPlants((prev) => {
      const next = new Set(prev);
      if (next.has(plantName)) {
        next.delete(plantName);
      } else {
        next.add(plantName);
      }
      return next;
    });
  };

  // Counts
  const normalCount = data.inverters.filter((i) => i.status === "normal").length;
  const warningCount = data.inverters.filter((i) => i.status === "warning").length;
  const faultCount = data.inverters.filter((i) => i.status === "fault" || i.status === "offline").length;

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
          <div className="p-2 rounded" style={{ background: "rgba(59, 130, 246, 0.15)" }}>
            <Cpu className="h-5 w-5" style={{ color: "var(--color-sentinel-blue)" }} />
          </div>
          <div>
            <h3 className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
              Inverter Fleet
            </h3>
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {data.inverter_count} inverters across {Object.keys(plantGroups).length} plants
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="text-xs px-2 py-0.5 rounded"
            style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--color-sentinel-green)" }}
          >
            {normalCount} OK
          </span>
          {warningCount > 0 && (
            <span
              className="text-xs px-2 py-0.5 rounded"
              style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--color-sentinel-amber)" }}
            >
              {warningCount} warn
            </span>
          )}
          {faultCount > 0 && (
            <span
              className="text-xs px-2 py-0.5 rounded"
              style={{ background: "rgba(220, 38, 38, 0.15)", color: "var(--color-sentinel-red)" }}
            >
              {faultCount} fault
            </span>
          )}
        </div>
      </div>

      {/* Plant Groups */}
      <div className="p-4 space-y-4">
        {Object.entries(plantGroups).map(([plantName, inverters]) => {
          const isCollapsed = collapsedPlants.has(plantName);
          const plantNormal = inverters.filter((i) => i.status === "normal").length;
          const plantTotal = inverters.length;

          return (
            <div key={plantName}>
              {/* Plant header */}
              <button
                onClick={() => togglePlant(plantName)}
                className="w-full flex items-center justify-between mb-2 cursor-pointer"
              >
                <div className="flex items-center gap-2">
                  {isCollapsed ? (
                    <ChevronDown className="h-3.5 w-3.5" style={{ color: "var(--color-sentinel-text-secondary)" }} />
                  ) : (
                    <ChevronUp className="h-3.5 w-3.5" style={{ color: "var(--color-sentinel-text-secondary)" }} />
                  )}
                  <span className="text-xs font-medium uppercase tracking-wider" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    {plantName}
                  </span>
                </div>
                <span className="text-[10px]" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                  {plantNormal}/{plantTotal} online
                </span>
              </button>

              {/* Inverter tiles */}
              {!isCollapsed && (
                <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-11 gap-1.5">
                  {inverters.map((inv) => (
                    <button
                      key={inv.inverter_id}
                      onClick={() => setSelectedInverter(selectedInverter?.inverter_id === inv.inverter_id ? null : inv)}
                      className="p-1.5 rounded text-center cursor-pointer transition-all hover:brightness-110"
                      style={{
                        background: "var(--color-sentinel-bg-secondary)",
                        border: getStatusBorder(inv.status),
                      }}
                      title={`${inv.name}: ${inv.current_power_kw.toFixed(1)} kW (${inv.status})`}
                    >
                      {/* Status dot */}
                      <div className="flex justify-center mb-1">
                        <div
                          className="w-2 h-2 rounded-full"
                          style={{ background: getStatusColor(inv.status) }}
                        />
                      </div>
                      {/* Name (short) */}
                      <div
                        className="text-[9px] font-medium truncate"
                        style={{ color: "var(--color-sentinel-text-primary)" }}
                      >
                        {inv.name.replace(/SUN2000-330KTL-|CL25 #|LUNA2000-213KTL-/, "").substring(0, 6)}
                      </div>
                      {/* Power */}
                      <div
                        className="text-[10px] font-semibold"
                        style={{ color: getStatusColor(inv.status) }}
                      >
                        {inv.current_power_kw.toFixed(0)}
                      </div>
                      <div className="text-[8px]" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                        kW
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Inverter Detail Flyout */}
      {selectedInverter && (
        <div
          className="mx-4 mb-4 p-4 rounded-md relative"
          style={{
            background: "var(--color-sentinel-bg-secondary)",
            border: getStatusBorder(selectedInverter.status),
          }}
        >
          <button
            onClick={() => setSelectedInverter(null)}
            className="absolute top-2 right-2 p-1 rounded hover:opacity-70"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            <X className="h-4 w-4" />
          </button>

          <div className="flex items-start gap-4 flex-wrap">
            <div>
              <h4 className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {selectedInverter.name}
              </h4>
              <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {selectedInverter.manufacturer} {selectedInverter.model} &mdash; {selectedInverter.plant_name}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3">
            <div className="p-2 rounded" style={{ background: "rgba(0,0,0,0.2)" }}>
              <div className="flex items-center gap-1 mb-1">
                <Zap className="h-3 w-3" style={{ color: getStatusColor(selectedInverter.status) }} />
                <span className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>Power</span>
              </div>
              <div className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {selectedInverter.current_power_kw.toFixed(1)} / {selectedInverter.rated_power_kw} kW
              </div>
            </div>
            <div className="p-2 rounded" style={{ background: "rgba(0,0,0,0.2)" }}>
              <div className="flex items-center gap-1 mb-1">
                <span className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>Efficiency</span>
              </div>
              <div
                className="text-sm font-semibold"
                style={{
                  color: selectedInverter.efficiency_percent >= 96
                    ? "var(--color-sentinel-green)"
                    : selectedInverter.efficiency_percent >= 90
                    ? "var(--color-sentinel-amber)"
                    : "var(--color-sentinel-red)",
                }}
              >
                {selectedInverter.efficiency_percent.toFixed(1)}%
              </div>
            </div>
            <div className="p-2 rounded" style={{ background: "rgba(0,0,0,0.2)" }}>
              <div className="flex items-center gap-1 mb-1">
                <Thermometer className="h-3 w-3" style={{ color: selectedInverter.temperature_c > 55 ? "var(--color-sentinel-red)" : "var(--color-sentinel-text-secondary)" }} />
                <span className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>Temp</span>
              </div>
              <div className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {selectedInverter.temperature_c.toFixed(0)}&deg;C
              </div>
            </div>
            <div className="p-2 rounded" style={{ background: "rgba(0,0,0,0.2)" }}>
              <div className="flex items-center gap-1 mb-1">
                <Sun className="h-3 w-3" style={{ color: "#FACC15" }} />
                <span className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>Daily Yield</span>
              </div>
              <div className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {selectedInverter.daily_yield_kwh.toFixed(0)} kWh
              </div>
            </div>
          </div>

          <div className="mt-2 text-[10px]" style={{ color: "var(--color-sentinel-text-disabled)" }}>
            {selectedInverter.mppt_count} MPPT trackers &middot; {selectedInverter.string_count} strings
          </div>
        </div>
      )}
    </div>
  );
}

export default InverterStatusMatrix;
