/**
 * ConciergeDashboardPage — Container orchestrating map + panels.
 *
 * State: selectedRoom, selectedSignalId.
 * Layout: ConciergeMap fills space, panels overlay right side.
 *
 * Phase 161-04 — Concierge Intelligence Dashboard.
 */

import { useState, useCallback } from "react";
import { RefreshCw } from "lucide-react";
import type { ConciergeRoom } from "../../lib/api";
import { ConciergeMap } from "./ConciergeMap";
import { SignalDrillDown } from "./SignalDrillDown";

interface ConciergeDashboardPageProps {
  siteId?: string;
  showHeader?: boolean;
  siteLabel?: string;
}

const DEFAULT_SITE = "S001";

function formatSiteLabel(siteId: string, siteLabel?: string): string {
  if (siteLabel) return siteLabel;
  if (siteId === "S001") return "Fairlands";
  if (siteId === "site-002") return "Sandton City";
  return siteId;
}

export function ConciergeDashboardPage({ siteId, showHeader = true, siteLabel }: ConciergeDashboardPageProps) {
  const effectiveSiteId = siteId || DEFAULT_SITE;
  const effectiveSiteLabel = formatSiteLabel(effectiveSiteId, siteLabel);
  const [selectedRoom, setSelectedRoom] = useState<ConciergeRoom | null>(null);
  const [selectedSignalId, setSelectedSignalId] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const handleSignalSelect = useCallback((room: ConciergeRoom, signalId: string) => {
    setSelectedRoom(room);
    setSelectedSignalId(signalId);
  }, []);

  const handleBackToRoom = useCallback(() => {
    setSelectedRoom(null);
    setSelectedSignalId(null);
  }, []);

  const handleRefresh = useCallback(() => {
    setRefreshKey((k) => k + 1);
    setSelectedRoom(null);
    setSelectedSignalId(null);
  }, []);

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {showHeader && (
        <HeaderBar siteId={effectiveSiteId} siteLabel={effectiveSiteLabel} onRefresh={handleRefresh} />
      )}

      {/* Map + overlay panels */}
      <div className="flex-1 min-h-0 relative">
        {/* Map fills available space */}
        <div className="absolute inset-0">
          <ConciergeMap
            key={refreshKey}
            siteId={effectiveSiteId}
            onSignalSelect={handleSignalSelect}
          />
        </div>

        {/* Signal drill-down (replaces room panel) */}
        {selectedRoom && selectedSignalId && (
          <SignalDrillDown
            siteId={effectiveSiteId}
            roomId={selectedRoom.room_id}
            signalId={selectedSignalId}
            onBack={handleBackToRoom}
            onResolved={handleRefresh}
          />
        )}
      </div>
    </div>
  );
}

// ---- Header bar subcomponent ----

function HeaderBar({ siteLabel, onRefresh }: { siteId: string; siteLabel: string; onRefresh: () => void }) {
  return (
    <div
      className="flex items-center justify-between px-5 py-3 flex-shrink-0"
      style={{
        background: "var(--color-sentinel-bg-primary, #0d1117)",
        borderBottom: "1px solid var(--color-sentinel-border, rgba(255,255,255,0.08))",
      }}
    >
      <div className="flex items-center gap-3">
        <h1 className="text-sm font-semibold text-gray-100">
          Concierge Intelligence
        </h1>
        <span className="text-[10px] text-gray-500 uppercase tracking-wider">
          {siteLabel}
        </span>
      </div>
      <button
        onClick={onRefresh}
        className="p-1.5 rounded hover:bg-gray-800 transition-colors text-gray-500 hover:text-gray-300"
        aria-label="Refresh"
        title="Refresh map"
      >
        <RefreshCw size={14} />
      </button>
    </div>
  );
}
