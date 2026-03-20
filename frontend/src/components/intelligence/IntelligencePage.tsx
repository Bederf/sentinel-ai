/**
 * IntelligencePage — Site-scoped concierge intelligence shell.
 *
 * The old cluster graph used a frozen Fairlands fixture and is no longer shown
 * in the operational side-panel view. This page now stays aligned with the
 * live building context only.
 */

import { useMemo } from "react";
import { Building2, Radar, ShieldAlert } from "lucide-react";
import { ConciergeDashboardPage } from "./ConciergeDashboardPage";
import { BuildingSelector } from "../BuildingSelector";
import { useBuildingsList } from "../../hooks/useBuildingsList";
import { setStoredSelectedSite } from "../../lib/siteSelection";

export function IntelligencePage({ siteId }: { siteId?: string }) {
  const { data: buildings = [] } = useBuildingsList();
  const selectedSiteId = useMemo(() => siteId || buildings[0]?.id || null, [buildings, siteId]);
  const selectedBuilding = useMemo(
    () => buildings.find((building) => building.id === selectedSiteId) ?? null,
    [buildings, selectedSiteId],
  );

  const handleSiteChange = (nextSiteId: string | null) => {
    if (!nextSiteId) return;
    setStoredSelectedSite(nextSiteId);
  };

  return (
    <div
      className="h-full min-h-0 overflow-hidden p-4 sm:p-5"
      style={{ background: "var(--color-grafana-bg-canvas)" }}
    >
      <section className="panel flex h-full min-h-0 flex-col overflow-hidden">
        <div className="panel-header gap-4 px-4 py-3 sm:px-5">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <div
                className="flex h-8 w-8 items-center justify-center rounded-md"
                style={{
                  background: "rgba(50, 116, 217, 0.12)",
                  border: "1px solid rgba(50, 116, 217, 0.24)",
                  color: "var(--color-grafana-blue)",
                }}
              >
                <Radar className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <h1 className="panel-title truncate">Meeting Room Intelligence</h1>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-[0.16em]">
                  <span style={{ color: "var(--color-grafana-text-secondary)" }}>Site scoped</span>
                  <span style={{ color: "var(--color-grafana-text-disabled)" }}>•</span>
                  <span style={{ color: "var(--color-grafana-text-primary)" }}>
                    {selectedBuilding?.name || "Select building"}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div className="flex w-full max-w-md flex-col gap-2 sm:w-[320px]">
            <div
              className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.16em]"
              style={{ color: "var(--color-grafana-text-secondary)" }}
            >
              <Building2 className="h-3.5 w-3.5" />
              <span>Building selector</span>
            </div>
            <BuildingSelector
              value={selectedSiteId || ""}
              onChange={handleSiteChange}
              sites={buildings}
            />
          </div>
        </div>

        <div
          className="flex items-center gap-2 border-b px-4 py-2 text-xs sm:px-5"
          style={{
            background: "var(--color-grafana-bg-primary)",
            borderColor: "var(--color-grafana-border)",
            color: "var(--color-grafana-text-secondary)",
          }}
        >
          <ShieldAlert className="h-3.5 w-3.5" style={{ color: "var(--color-grafana-yellow)" }} />
          <span>Room-linked intelligence from bookings, occupancy, and intake email threads.</span>
        </div>

        <div className="min-h-0 flex-1">
          <ConciergeDashboardPage
            siteId={selectedSiteId || undefined}
            siteLabel={selectedBuilding?.name}
            showHeader={false}
          />
        </div>
      </section>
    </div>
  );
}
