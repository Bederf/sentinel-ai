/**
 * SolarDashboard - Full Solar & BESS Dashboard View
 *
 * Brings together all 6 solar components in a responsive grid layout
 * with a building selector for multi-site support.
 *
 * Layout:
 *   Row 1: Overview Panel | BESS Status | Energy Flow Diagram
 *   Row 2: Inverter Status Matrix (full width)
 *   Row 3: Financial Report | Forecast vs Actual Chart
 */

import { useState, useEffect, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Sun, Building2, ChevronDown, RefreshCw } from "lucide-react";
import { useSimulation } from "../../contexts/SimulationContext";
import { fetchSolarSites } from "../../lib/solarApi";
import type { SolarSite } from "../../lib/solarApi";
import { useModuleAccess } from "../../hooks/useModuleAccess";
import { PageLoading } from "../PageLoading";
import { SolarOverviewPanel } from "./SolarOverviewPanel";
import { BESSStatusPanel } from "./BESSStatusPanel";
import { InverterStatusMatrix } from "./InverterStatusMatrix";
import { EnergyFlowDiagram } from "./EnergyFlowDiagram";
import { SolarFinancialReport } from "./SolarFinancialReport";
import { ForecastActualChart } from "./ForecastActualChart";
import { SolarAnnualCard } from "./SolarAnnualCard";

/**
 * SolarDashboard - Main solar & BESS monitoring view
 *
 * Components use React Query hooks for automatic caching, deduplication, and
 * request management. The refresh button invalidates all solar queries.
 *
 * Layout:
 * - Row 1: Overview (generation, performance) | BESS (SOC, mode) | Energy Flow
 * - Row 2: Inverter Status Matrix (full width)
 * - Row 3: Financial Report | Forecast vs Actual Chart
 */
export function SolarDashboard() {
  const queryClient = useQueryClient();
  const [solarSites, setSolarSites] = useState<SolarSite[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string>("");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const { isActive: isSolarActive } = useModuleAccess('solar');

  // Get simulation context for live solar efficiency data
  const { running: isSimulationRunning, solarEfficiency, cloudCover, simulatedHour, daysSimulated } = useSimulation();

  // Refetch all solar data when module is activated (eliminates 30s stale data lag)
  useEffect(() => {
    if (isSolarActive) {
      queryClient.invalidateQueries({ queryKey: ['solar-overview'] });
      queryClient.invalidateQueries({ queryKey: ['solar-bess'] });
      queryClient.invalidateQueries({ queryKey: ['solar-inverters'] });
      queryClient.invalidateQueries({ queryKey: ['solar-performance'] });
      queryClient.invalidateQueries({ queryKey: ['solar-financial'] });
    }
  }, [isSolarActive, queryClient]);

  // Fetch solar sites on mount
  useEffect(() => {
    fetchSolarSites()
      .then((sites) => {
        // Deduplicate sites by site_id
        const uniqueSites = Array.from(
          new Map(sites.map((site) => [site.site_id, site])).values()
        );
        setSolarSites(uniqueSites);
        if (uniqueSites.length > 0 && !selectedSiteId) {
          setSelectedSiteId(uniqueSites[0].site_id);
        }
      })
      .catch(() => {
        // Fallback if API not available
        // Fallback: empty state when API is unavailable
        setSolarSites([]);
        // selectedSiteId stays empty if no API data
      });
  }, [selectedSiteId]);

  // Refetch all solar data when module is activated
  useEffect(() => {
    if (isSolarActive) {
      queryClient.invalidateQueries({ queryKey: ['solar-overview'] });
      queryClient.invalidateQueries({ queryKey: ['solar-bess'] });
      queryClient.invalidateQueries({ queryKey: ['solar-inverters'] });
      queryClient.invalidateQueries({ queryKey: ['solar-performance'] });
      queryClient.invalidateQueries({ queryKey: ['solar-financial'] });
    }
  }, [isSolarActive, queryClient]);

  /**
   * Refresh all solar queries via React Query
   *
   * Invalidates all solar queries (overview, BESS, inverters, performance, financial)
   * which triggers refetch of stale data. This respects React Query's stale time,
   * so in-cache data is immediately refetched while fresh data is used as-is.
   */
  const handleRefresh = useCallback(() => {
    setIsRefreshing(true);
    // Invalidate all solar-related queries
    queryClient.invalidateQueries({ queryKey: ['solar-overview'] });
    queryClient.invalidateQueries({ queryKey: ['solar-bess'] });
    queryClient.invalidateQueries({ queryKey: ['solar-inverters'] });
    queryClient.invalidateQueries({ queryKey: ['solar-performance'] });
    queryClient.invalidateQueries({ queryKey: ['solar-financial'] });
    setTimeout(() => setIsRefreshing(false), 1000);
  }, [queryClient]);

  return (
    <div
      className="h-full overflow-y-auto p-4 md:p-6"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div
            className="p-2 rounded"
            style={{ background: "rgba(245, 158, 11, 0.15)" }}
          >
            <Sun className="h-5 w-5" style={{ color: "var(--color-sentinel-amber)" }} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1
                className="text-2xl font-bold"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Solar &amp; BESS
              </h1>
              {isSimulationRunning && (
                <div className="px-2 py-0.5 rounded text-xs font-medium"
                  style={{
                    background: 'rgba(250, 204, 21, 0.15)',
                    color: '#FACC15',
                  }}
                >
                  ☀️ Live • {solarEfficiency?.toFixed(0)}% efficiency
                </div>
              )}
            </div>
            <p
              className="text-sm"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              {isSimulationRunning
                ? `Live generation data \u2022 Hour ${simulatedHour}:00 (Day ${daysSimulated}/365) \u2022 ${cloudCover?.toFixed(0)}% cloud cover`
                : 'Generation, Storage, Dispatch &amp; Financial Performance'
              }
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Building Selector */}
          <div className="relative">
            <Building2
              className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            />
            <ChevronDown
              className="absolute right-2 top-1/2 transform -translate-y-1/2 h-3 w-3 pointer-events-none"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            />
            <select
              value={selectedSiteId}
              onChange={(e) => setSelectedSiteId(e.target.value)}
              className="pl-9 pr-7 py-1.5 text-sm rounded appearance-none cursor-pointer"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                border: "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-primary)",
                outline: "none",
                minWidth: "250px",
              }}
            >
              {solarSites.map((site) => (
                <option key={site.site_id} value={site.site_id}>
                  {site.site_name} — {site.site_name}
                </option>
              ))}
            </select>
          </div>

          {/* Refresh */}
          <button
            onClick={handleRefresh}
            className="p-2 rounded"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-secondary)",
              cursor: "pointer",
            }}
            title="Refresh all panels"
          >
            <RefreshCw
              className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`}
            />
          </button>
        </div>
      </div>

      {/* Row 1: Overview + BESS + Energy Flow */}
      {!selectedSiteId ? (
        <PageLoading message="Loading solar sites..." />
      ) : (
      <>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
        <div
          className="rounded-md overflow-hidden"
          style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
        >
          <SolarOverviewPanel siteId={selectedSiteId} />
        </div>
        <div
          className="rounded-md overflow-hidden"
          style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
        >
          <BESSStatusPanel siteId={selectedSiteId} />
        </div>
        <div
          className="rounded-md overflow-hidden"
          style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
        >
          <EnergyFlowDiagram siteId={selectedSiteId} />
        </div>
      </div>

      {/* Row 2: Inverter Matrix (full width) */}
      <div className="mb-4">
        <div
          className="rounded-md overflow-hidden"
          style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
        >
          <InverterStatusMatrix siteId={selectedSiteId} />
        </div>
      </div>

      {/* Row 3: Financial Report + Forecast Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <div
          className="rounded-md overflow-hidden"
          style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
        >
          <SolarFinancialReport siteId={selectedSiteId} />
        </div>
        <div
          className="rounded-md overflow-hidden"
          style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
        >
          <ForecastActualChart siteId={selectedSiteId} />
        </div>
      </div>

      {/* Row 4: Annual Performance Summary (365 days) */}
      <div className="mb-4">
        <div
          className="rounded-md overflow-hidden"
          style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
        >
          <SolarAnnualCard siteId={selectedSiteId} />
        </div>
      </div>
      </>
      )}
    </div>
  );
}

export default SolarDashboard;
