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

interface SolarOverviewPanelProps {
  siteId: string;
}

export function SolarOverviewPanel({ siteId }: SolarOverviewPanelProps) {
  const [overview, setOverview] = useState<SolarOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const data = await fetchSolarOverview(siteId);
      setOverview(data);
      setError(null);
    } catch (err) {
      console.error("Failed to load solar overview:", err);
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

  const generationPercent = overview.installed_capacity_kwp > 0
    ? (overview.current_generation_kw / overview.installed_capacity_kwp) * 100
    : 0;

  const yieldPercent = overview.expected_daily_yield_kwh > 0
    ? (overview.daily_yield_kwh / overview.expected_daily_yield_kwh) * 100
    : 0;

  const prColor = overview.performance_ratio >= 0.8
    ? "var(--color-sentinel-green)"
    : overview.performance_ratio >= 0.7
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
              {overview.site_name} &mdash; {overview.installed_capacity_kwp.toLocaleString()} kWp installed
            </span>
          </div>
        </div>
        <span
          className="text-xs px-2 py-1 rounded"
          style={{
            background: overview.current_generation_kw > 0 ? "rgba(16, 185, 129, 0.15)" : "rgba(107, 114, 128, 0.15)",
            color: overview.current_generation_kw > 0 ? "var(--color-sentinel-green)" : "var(--color-sentinel-text-secondary)",
          }}
        >
          {overview.current_generation_kw > 0 ? "Generating" : "Offline"}
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
            {overview.current_generation_kw.toFixed(0)}
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
                {overview.installed_capacity_kwp.toLocaleString()} kWp
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
            {overview.daily_yield_kwh.toLocaleString(undefined, { maximumFractionDigits: 0 })}
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
              {yieldPercent.toFixed(0)}% of expected ({overview.expected_daily_yield_kwh.toLocaleString(undefined, { maximumFractionDigits: 0 })} kWh)
            </div>
          </div>
        </div>

        {/* Performance Ratio */}
        <div className="p-3 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
          <div className="flex items-center gap-2 mb-2">
            {overview.performance_ratio >= 0.8 ? (
              <TrendingUp className="h-4 w-4" style={{ color: "var(--color-sentinel-green)" }} />
            ) : overview.performance_ratio >= 0.7 ? (
              <Minus className="h-4 w-4" style={{ color: "var(--color-sentinel-amber)" }} />
            ) : (
              <TrendingDown className="h-4 w-4" style={{ color: "var(--color-sentinel-red)" }} />
            )}
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Performance Ratio
            </span>
          </div>
          <div className="text-2xl font-bold" style={{ color: prColor }}>
            {(overview.performance_ratio * 100).toFixed(1)}
            <span className="text-sm font-normal ml-1">%</span>
          </div>
          <div className="text-[10px] mt-2" style={{ color: "var(--color-sentinel-text-disabled)" }}>
            Target: 80% &mdash; Self-consumption: {overview.self_consumption_percent.toFixed(0)}%
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
            {formatZAR(overview.estimated_savings_today_zar)}
          </div>
          <div className="text-[10px] mt-2" style={{ color: "var(--color-sentinel-text-disabled)" }}>
            Grid import: {overview.grid_import_kw.toFixed(0)} kW | Export: {overview.grid_export_kw.toFixed(0)} kW
          </div>
        </div>
      </div>
    </div>
  );
}

export default SolarOverviewPanel;
