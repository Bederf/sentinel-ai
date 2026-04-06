/**
 * ConciergeDashboardPage — Container orchestrating map + panels.
 *
 * State: selectedRoom, selectedSignalId.
 * Layout: ConciergeMap fills space, panels overlay right side.
 *
 * Phase 161-04 — Concierge Intelligence Dashboard.
 */

import { Suspense, lazy, useCallback, useState } from "react";
import { RefreshCw } from "lucide-react";
import type { ConciergeRoom } from "../../lib/api";

const ConciergeMap = lazy(() =>
  import("./ConciergeMap").then((module) => ({ default: module.ConciergeMap })),
);
const SignalDrillDown = lazy(() =>
  import("./SignalDrillDown").then((module) => ({ default: module.SignalDrillDown })),
);

interface ConciergeDashboardPageProps {
  siteId?: string;
  showHeader?: boolean;
  siteLabel?: string;
}

const DEFAULT_SITE = "S001";

function ConciergeSurfaceFallback({ message = "Loading concierge intelligence..." }: { message?: string }) {
  return (
    <div className="flex h-full items-center justify-center text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
      {message}
    </div>
  );
}

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
        <HeaderBar siteLabel={effectiveSiteLabel} onRefresh={handleRefresh} />
      )}

      {/* Map + overlay panels */}
      <div className="flex-1 min-h-0 relative">
        {/* Map fills available space */}
        <div className="absolute inset-0">
          <Suspense fallback={<ConciergeSurfaceFallback />}>
            <ConciergeMap
              key={refreshKey}
              siteId={effectiveSiteId}
              onSignalSelect={handleSignalSelect}
            />
          </Suspense>
        </div>

        {/* Signal drill-down (replaces room panel) */}
        {selectedRoom && selectedSignalId && (
          <Suspense fallback={<ConciergeSurfaceFallback message="Loading signal detail..." />}>
            <SignalDrillDown
              siteId={effectiveSiteId}
              roomId={selectedRoom.room_id}
              signalId={selectedSignalId}
              room={selectedRoom}
              onSignalSelect={(nextSignalId) => setSelectedSignalId(nextSignalId)}
              onBack={handleBackToRoom}
              onResolved={handleRefresh}
            />
          </Suspense>
        )}
      </div>
    </div>
  );
}

// ---- Header bar subcomponent ----

function HeaderBar({ siteLabel, onRefresh }: { siteLabel: string; onRefresh: () => void }) {
  return (
    <div
      className="flex items-center justify-between px-5 py-3 flex-shrink-0"
      style={{
        background: "var(--color-sentinel-bg-panel)",
        borderBottom: "1px solid var(--color-sentinel-border)",
      }}
    >
      <div className="flex items-center gap-3">
        <h1 className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
          Concierge Intelligence
        </h1>
        <span className="text-[10px] uppercase tracking-wider" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          {siteLabel}
        </span>
      </div>
      <button
        onClick={onRefresh}
        className="p-1.5 rounded-lg transition-colors hover:brightness-110"
        style={{
          background: "var(--color-sentinel-bg-secondary)",
          color: "var(--color-sentinel-text-secondary)",
          border: "1px solid var(--color-sentinel-border)",
        }}
        aria-label="Refresh"
        title="Refresh map"
      >
        <RefreshCw size={14} />
      </button>
    </div>
  );
}
