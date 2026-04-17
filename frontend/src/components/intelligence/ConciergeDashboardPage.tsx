/**
 * ConciergeDashboardPage — Container orchestrating map + panels.
 *
 * State: selectedRoom, selectedSignalId.
 * Layout: ConciergeMap fills space, panels overlay right side.
 *
 * Phase 161-04 — Concierge Intelligence Dashboard.
 */

import { useState, useCallback, useEffect, useRef } from "react";
import React from "react";
import { RefreshCw } from "lucide-react";
import { gsap } from "gsap";
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
  const [panelEntered, setPanelEntered] = useState(false);

  // Animation refs
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const drillPanelRef = useRef<HTMLDivElement>(null);
  const headerRef = useRef<HTMLDivElement>(null);

  // GSAP entrance for map
  useEffect(() => {
    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReduced) { setPanelEntered(true); return; }

    const ctx = gsap.context(() => {
      gsap.fromTo(mapContainerRef.current,
        { opacity: 0, scale: 0.97 },
        { opacity: 1, scale: 1, duration: 0.6, ease: "power3.out", delay: 0.1 }
      );
      if (headerRef.current) {
        gsap.fromTo(headerRef.current,
          { y: -16, opacity: 0 },
          { y: 0, opacity: 1, duration: 0.4, ease: "power3.out" }
        );
      }
    });
    setPanelEntered(true);
    return () => ctx.revert();
  }, []);

  // GSAP drill panel entrance
  useEffect(() => {
    if (!panelEntered) return;
    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReduced) return;

    if (selectedRoom && selectedSignalId && drillPanelRef.current) {
      gsap.fromTo(drillPanelRef.current,
        { x: 40, opacity: 0 },
        { x: 0, opacity: 1, duration: 0.35, ease: "power3.out" }
      );
    }
  }, [selectedRoom, selectedSignalId, panelEntered]);

  const handleSignalSelect = useCallback((room: ConciergeRoom, signalId: string) => {
    setSelectedRoom(room);
    setSelectedSignalId(signalId);
  }, []);

  const handleBackToRoom = useCallback(() => {
    if (drillPanelRef.current) {
      gsap.to(drillPanelRef.current, {
        x: 40, opacity: 0, duration: 0.22, ease: "power2.in",
        onComplete: () => {
          setSelectedRoom(null);
          setSelectedSignalId(null);
        },
      });
    } else {
      setSelectedRoom(null);
      setSelectedSignalId(null);
    }
  }, []);

  const handleRefresh = useCallback(() => {
    setRefreshKey((k) => k + 1);
    setSelectedRoom(null);
    setSelectedSignalId(null);
  }, []);

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {showHeader && (
        <HeaderBar
          ref={headerRef}
          siteId={effectiveSiteId}
          siteLabel={effectiveSiteLabel}
          onRefresh={handleRefresh}
        />
      )}

      {/* Map + overlay panels */}
      <div className="flex-1 min-h-0 relative">
        {/* Map fills available space */}
        <div ref={mapContainerRef} className="absolute inset-0 opacity-0">
          <ConciergeMap
            key={refreshKey}
            siteId={effectiveSiteId}
            onSignalSelect={handleSignalSelect}
          />
        </div>

        {/* Signal drill-down (replaces room panel) */}
        {selectedRoom && selectedSignalId && (
          <div ref={drillPanelRef} className="absolute right-0 top-0 h-full w-full sm:w-[480px] z-20 opacity-0">
            <SignalDrillDown
              siteId={effectiveSiteId}
              roomId={selectedRoom.room_id}
              signalId={selectedSignalId}
              onBack={handleBackToRoom}
              onResolved={handleRefresh}
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ---- Header bar subcomponent ----

const HeaderBar = React.forwardRef<HTMLDivElement, { siteId: string; siteLabel: string; onRefresh: () => void }>(
  function HeaderBar({ siteLabel, onRefresh }, ref) {
    return (
      <div
        ref={ref}
        className="flex items-center justify-between px-5 py-3 flex-shrink-0 opacity-0"
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
);
