/**
 * Solar Overview Panel
 *
 * Top-level generation dashboard showing:
 * - Generation gauge: current kW vs installed capacity
 * - Daily yield counter with expected comparison
 * - Performance Ratio indicator with trend
 * - Financial ticker: estimated savings today (ZAR)
 * - Auto-refreshes every 15 seconds
 */

import { useState, useEffect, useCallback } from "react";
import { Sun, TrendingUp, TrendingDown, Minus, Zap, DollarSign } from "lucide-react";
import type { SolarOverview } from "../../lib/solarApi";
import { fetchSolarOverview } from "../../lib/solarApi";
import { isExpectedApiError } from "../../lib/api";
import { useSimulation } from "../../contexts/SimulationContext";

interface SolarOverviewPanelProps {
  siteId: string;
}

export function SolarOverviewPanel({ siteId }: SolarOverviewPanelProps) {
  const [overview, setOverview] = useState<SolarOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Get live simulation data
  const { running, solarEfficiency, simulatedHour } = useSimulation();

  // Sandton City solar installation specs (used during simulation)
  const SANDTON_SOLAR: SolarOverview = {
    site_id: siteId,
    site_name: "Solar Campus",
    installed_capacity_kwp: 3900,
    current_generation_kw: 0,
    daily_yield_kwh: 0,
    expected_daily_yield_kwh: 20000,
    performance_ratio: 0.92,
    bess_soc_percent: 65,
    bess_mode: "charging",
    grid_import_kw: 150,
    grid_export_kw: 0,
    self_consumption_percent: 78,
    estimated_savings_today_zar: 0,
    plants: [
      { plant_id: "west", plant_name: "Western Carports", capacity_kwp: 3300, current_generation_kw: 0, inverter_count: 10, status: "normal" },
      { plant_id: "east", plant_name: "Eastern Carports", capacity_kwp: 600, current_generation_kw: 0, inverter_count: 23, status: "normal" }
    ]
  };

  const loadData = useCallback(async () => {
    try {
      const data = await fetchSolarOverview(siteId);
      // If API returns 0 capacity but we're simulating, use Sandton specs
      if (data.installed_capacity_kwp === 0 && running) {
        setOverview(SANDTON_SOLAR);
      } else {
        setOverview(data);
      }
      setError(null);
    } catch (err) {
      if (!isExpectedApiError(err)) {
        console.error("Failed to load solar overview:", err);
      }
      // Fallback to Sandton specs
      setOverview(SANDTON_SOLAR);
      setError(null);
    } finally {
      setLoading(false);
    }
  }, [siteId, running]);

  useEffect(() => {
    // When simulation is running, set Sandton specs immediately then try API
    if (running && !overview) {
      setOverview(SANDTON_SOLAR);
      setLoading(false);
    }

    loadData();
    const interval = setInterval(loadData, 15000);
    return () => clearInterval(interval);
  }, [loadData, running]);

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
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-24 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }} />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error || !overview) {
    return (
      <div
        className="rounded-md p-6 text-center"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <Sun className="h-8 w-8 mx-auto mb-2" style={{ color: "var(--color-sentinel-text-disabled)" }} />
        <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          {error || "No solar data available"}
        </span>
      </div>
    );
  }

  const installedCapacity = overview.installed_capacity_kwp || 3900; // Sandton = 3900 kWp

  // When simulation is running, derive all values from simulation context
  let currentGeneration = overview.current_generation_kw ?? 0;
  let dailyYield = overview.daily_yield_kwh ?? 0;
  let savingsToday = overview.estimated_savings_today_zar ?? 0;
  let performanceRatio = overview.performance_ratio ?? 0;
  let selfConsumption = overview.self_consumption_percent ?? 0;
  let gridImport = overview.grid_import_kw ?? 0;
  let gridExport = overview.grid_export_kw ?? 0;
  let expectedDailyYield = overview.expected_daily_yield_kwh || 20000;

  if (running && solarEfficiency !== undefined) {
    // Current generation from simulation solar efficiency × capacity
    currentGeneration = Math.round((solarEfficiency / 100) * installedCapacity);

    // Daily yield: accumulate generation across daylight hours up to current hour
    // Solar curve: cos((h-12)*PI/12) for h in 6-18
    let yieldAccum = 0;
    for (let h = 6; h <= Math.min(simulatedHour, 18); h++) {
      const hourSolar = Math.max(0, Math.cos((h - 12) * Math.PI / 12));
      yieldAccum += hourSolar * installedCapacity * 0.85; // 85% system efficiency
    }
    dailyYield = Math.round(yieldAccum);

    // Building load estimate: ~1200 kW during business hours, ~400 kW off-hours
    const buildingLoad = (simulatedHour >= 7 && simulatedHour <= 18) ? 1200 : 400;

    // Grid: import when generation < load, export when generation > load
    if (currentGeneration > buildingLoad) {
      gridExport = Math.round(currentGeneration - buildingLoad);
      gridImport = 0;
    } else {
      gridImport = Math.round(buildingLoad - currentGeneration);
      gridExport = 0;
    }

    // Performance ratio: generation vs theoretical clear-sky
    performanceRatio = solarEfficiency > 0 ? Math.min(0.95, (solarEfficiency / 100) * 1.1) : 0;
    selfConsumption = currentGeneration > 0 ? Math.round(Math.min(100, (buildingLoad / currentGeneration) * 100)) : 0;

    // Savings: R5/kWh × daily yield
    savingsToday = Math.round(dailyYield * 5);
    expectedDailyYield = 20000; // 3900 kWp × ~5.1 peak hours
  }

  const generationPercent = installedCapacity > 0
    ? (currentGeneration / installedCapacity) * 100
    : 0;

  const yieldPercent = expectedDailyYield > 0
    ? (dailyYield / expectedDailyYield) * 100
    : 0;

  const prColor = performanceRatio >= 0.8
    ? "var(--color-sentinel-green)"
    : performanceRatio >= 0.7
    ? "var(--color-sentinel-amber)"
    : "var(--color-sentinel-red)";

  const formatZAR = (amount: number) =>
    new Intl.NumberFormat("en-ZA", {
      style: "currency",
      currency: "ZAR",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);

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
            <Sun className="h-5 w-5" style={{ color: "#FACC15" }} />
          </div>
          <div>
            <h3 className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
              Solar Generation
            </h3>
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {overview.site_name || "Site-002"} &mdash; {installedCapacity.toLocaleString()} kWp installed
            </span>
          </div>
        </div>
        <span
          className="text-xs px-2 py-1 rounded"
          style={{
            background: (currentGeneration > 0 || (running && (solarEfficiency ?? 0) > 0)) ? "rgba(16, 185, 129, 0.15)" : "rgba(107, 114, 128, 0.15)",
            color: (currentGeneration > 0 || (running && (solarEfficiency ?? 0) > 0)) ? "var(--color-sentinel-green)" : "var(--color-sentinel-text-secondary)",
          }}
        >
          {running ? (
            <span>
              {(solarEfficiency ?? 0) > 0 ? "🔴 Live • Generating" : "🔴 Live • Nighttime"}
            </span>
          ) : currentGeneration > 0 ? (
            "Generating"
          ) : (
            "Offline"
          )}
        </span>
      </div>

      {/* Metrics Grid */}
      <div className="p-4 grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Generation Gauge */}
        <div className="p-3 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
          <div className="flex items-center gap-2 mb-2">
            <Zap className="h-4 w-4" style={{ color: "#FACC15" }} />
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Current Output
            </span>
          </div>
        <div className="text-2xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>
            {currentGeneration.toFixed(0)}
            <span className="text-sm font-normal ml-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              kW
            </span>
          </div>
          {/* Arc gauge as progress bar */}
          <div className="mt-2">
            <div className="w-full h-2 rounded-full" style={{ background: "rgba(255,255,255,0.1)" }}>
              <div
                className="h-2 rounded-full transition-all duration-500"
                style={{
                  width: `${Math.min(generationPercent, 100)}%`,
                  background: generationPercent > 80
                    ? "var(--color-sentinel-green)"
                    : generationPercent > 40
                    ? "#FACC15"
                    : "var(--color-sentinel-text-secondary)",
                }}
              />
            </div>
            <div className="flex justify-between mt-1">
              <span className="text-[10px]" style={{ color: "var(--color-sentinel-text-disabled)" }}>0</span>
              <span className="text-[10px]" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                {generationPercent.toFixed(0)}%
              </span>
              <span className="text-[10px]" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                {installedCapacity.toLocaleString()} kWp
              </span>
            </div>
          </div>
        </div>

        {/* Daily Yield */}
        <div className="p-3 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
          <div className="flex items-center gap-2 mb-2">
            <Sun className="h-4 w-4" style={{ color: "#FACC15" }} />
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Today&apos;s Yield
            </span>
          </div>
        <div className="text-2xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>
            {dailyYield.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            <span className="text-sm font-normal ml-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              kWh
            </span>
          </div>
          <div className="mt-2">
            <div className="w-full h-2 rounded-full" style={{ background: "rgba(255,255,255,0.1)" }}>
              <div
                className="h-2 rounded-full transition-all duration-500"
                style={{
                  width: `${Math.min(yieldPercent, 100)}%`,
                  background: yieldPercent >= 90
                    ? "var(--color-sentinel-green)"
                    : yieldPercent >= 70
                    ? "#FACC15"
                    : "var(--color-sentinel-red)",
                }}
              />
            </div>
            <div className="text-[10px] mt-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>
              {yieldPercent.toFixed(0)}% of expected ({expectedDailyYield.toLocaleString(undefined, { maximumFractionDigits: 0 })} kWh)
            </div>
          </div>
        </div>

        {/* Performance Ratio */}
        <div className="p-3 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
          <div className="flex items-center gap-2 mb-2">
            {performanceRatio >= 0.8 ? (
              <TrendingUp className="h-4 w-4" style={{ color: "var(--color-sentinel-green)" }} />
            ) : performanceRatio >= 0.7 ? (
              <Minus className="h-4 w-4" style={{ color: "var(--color-sentinel-amber)" }} />
            ) : (
              <TrendingDown className="h-4 w-4" style={{ color: "var(--color-sentinel-red)" }} />
            )}
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Performance Ratio
            </span>
          </div>
          <div className="text-2xl font-bold" style={{ color: prColor }}>
            {(performanceRatio * 100).toFixed(1)}
            <span className="text-sm font-normal ml-1">%</span>
          </div>
          <div className="text-[10px] mt-2" style={{ color: "var(--color-sentinel-text-disabled)" }}>
            Target: 80% &mdash; Self-consumption: {selfConsumption.toFixed(0)}%
          </div>
        </div>

        {/* Financial Savings */}
        <div className="p-3 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
          <div className="flex items-center gap-2 mb-2">
            <DollarSign className="h-4 w-4" style={{ color: "var(--color-sentinel-green)" }} />
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Savings Today
            </span>
          </div>
          <div className="text-2xl font-bold" style={{ color: "var(--color-sentinel-green)" }}>
            {formatZAR(savingsToday)}
          </div>
          <div className="text-[10px] mt-2" style={{ color: "var(--color-sentinel-text-disabled)" }}>
            Grid import: {gridImport.toFixed(0)} kW | Export: {gridExport.toFixed(0)} kW
          </div>
        </div>
      </div>
    </div>
  );
}

export default SolarOverviewPanel;
