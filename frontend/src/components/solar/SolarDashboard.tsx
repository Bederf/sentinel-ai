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
import { Sun, Building2, ChevronDown, RefreshCw } from "lucide-react";
import { fetchSolarSites } from "../../lib/solarApi";
import type { SolarSite } from "../../lib/solarApi";
import { SolarOverviewPanel } from "./SolarOverviewPanel";
import { BESSStatusPanel } from "./BESSStatusPanel";
import { InverterStatusMatrix } from "./InverterStatusMatrix";
import { EnergyFlowDiagram } from "./EnergyFlowDiagram";
import { SolarFinancialReport } from "./SolarFinancialReport";
import { ForecastActualChart } from "./ForecastActualChart";

export function SolarDashboard() {
  const [solarSites, setSolarSites] = useState<SolarSite[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string>("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Fetch solar sites on mount
  useEffect(() => {
    fetchSolarSites()
      .then((sites) => {
        setSolarSites(sites);
        if (sites.length > 0 && !selectedSiteId) {
          setSelectedSiteId(sites[0].site_id);
        }
      })
      .catch(() => {
        // Fallback if API not available
        setSolarSites([
          { site_id: "site-002", site_name: "Sandton City Office Tower", plants: 2, connectors: 3, last_poll: null },
        ]);
        if (!selectedSiteId) setSelectedSiteId("site-002");
      });
  }, []);

  const handleRefresh = useCallback(() => {
    setIsRefreshing(true);
    setRefreshKey((k) => k + 1);
    setTimeout(() => setIsRefreshing(false), 1000);
  }, []);

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
            <h2
              className="text-lg font-semibold"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Solar & BESS
            </h2>
            <p
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              Generation, storage, dispatch, and financial performance
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
                minWidth: "200px",
              }}
            >
              {solarSites.map((site) => (
                <option key={site.site_id} value={site.site_id}>
                  {site.site_name}
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
        <div className="text-center py-12" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Loading solar sites...
        </div>
      ) : (
      <>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4" key={refreshKey}>
        <div
          className="glass-panel overflow-hidden"
        >
          <SolarOverviewPanel siteId={selectedSiteId} />
        </div>
        <div
          className="glass-panel overflow-hidden"
        >
          <BESSStatusPanel siteId={selectedSiteId} />
        </div>
        <div
          className="glass-panel overflow-hidden"
        >
          <EnergyFlowDiagram siteId={selectedSiteId} />
        </div>
      </div>

      {/* Row 2: Inverter Matrix (full width) */}
      <div className="mb-4">
        <div
          className="glass-panel overflow-hidden"
        >
          <InverterStatusMatrix siteId={selectedSiteId} />
        </div>
      </div>

      {/* Row 3: Financial Report + Forecast Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div
          className="glass-panel overflow-hidden"
        >
          <SolarFinancialReport siteId={selectedSiteId} />
        </div>
        <div
          className="glass-panel overflow-hidden"
        >
          <ForecastActualChart siteId={selectedSiteId} />
        </div>
      </div>
      </>
      )}
    </div>
  );
}

export default SolarDashboard;
