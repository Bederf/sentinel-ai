/**
 * ArcadeView — spatial intelligence interface for the building Overview tab.
 * Fetches DecisionMomentPayload from /api/decisions/current/{siteId} on mount + every 30s.
 * Renders FloorStack + SummaryStrip inside the building overview shell.
 * Phase 167-03.
 */

import { useState, useEffect, useRef } from "react";
import { authorizedFetch } from "@/lib/api";
import { buildCurrentDecisionUrl } from "@/lib/decisions";
import { FloorStack } from "./FloorStack";
import type { FloorStackProps } from "./FloorStack";
import { SummaryStrip } from "./SummaryStrip";
import { ContextPanel } from "./ContextPanel";

// ─── Types ──────────────────────────────────────────────────────────────────

interface IncidentFloor {
  stack_index: number;
  svg_y_pct: number;
  affected: boolean;
}

interface BuildingMetadata {
  floors_count?: number;
  floor_labels?: Record<string, string>;
  floor_stack_order?: string[];
  has_spatial_data?: boolean;
  floor_stack?: unknown[];
  deployment_mode?: string;
  dismiss_window_minutes?: number;
  equipment_count?: number | null;
  active_risk_count?: number | null;
  health_pct?: number | null;
}

interface DecisionPayload {
  building_id: string;
  renderer_hint?: string;
  urgency_score?: number;
  alert_text?: string;
  reasoning_summary?: string;
  recommended_action?: string;
  time_to_discomfort?: number | null;
  active_incident_map?: Record<string, IncidentFloor>;
  building_metadata?: BuildingMetadata;
}

// ─── Props ───────────────────────────────────────────────────────────────────

export interface ArcadeViewProps {
  siteId: string;
  onModuleDisplayChange?: (moduleDisplay: Record<string, string>) => void;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const POLL_INTERVAL_MS = 30_000;
const DEFAULT_FLOOR_ORDER = ["R", "L2", "L1", "L0", "G", "B1"];

function SkeletonFloors({ count }: { count: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          style={{
            height: 40,
            borderRadius: 4,
            background: "rgba(255,255,255,0.05)",
            animation: "pulse 1.5s ease-in-out infinite",
          }}
        />
      ))}
    </div>
  );
}

// ─── Component ───────────────────────────────────────────────────────────────

export function ArcadeView({ siteId, onModuleDisplayChange }: ArcadeViewProps) {
  const [payload, setPayload] = useState<DecisionPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Trigger state (floor click → /api/decisions/trigger + module_display for overview sections)
  const [selectedFloor, setSelectedFloor] = useState<string | null>(null);
  const [contextOpen, setContextOpen] = useState(false);
  const [triggerModuleDisplay, setTriggerModuleDisplay] = useState<Record<string, string>>({});
  const [triggerLoading, setTriggerLoading] = useState(false);
  const [triggerFailed, setTriggerFailed] = useState(false);

  const handleFloorClick = async (floorId: string) => {
    setSelectedFloor(floorId);
    setContextOpen(true);
    setTriggerLoading(true);
    setTriggerFailed(false);
    setTriggerModuleDisplay({});
    try {
      const resp = await authorizedFetch(`/api/decisions/trigger/${encodeURIComponent(siteId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trigger_type: "floor", context: { floor_id: floorId } }),
      });
      if (resp.ok) {
        const data = await resp.json();
        const moduleDisplay: Record<string, string> = data.module_display ?? {};
        setTriggerModuleDisplay(moduleDisplay);
        onModuleDisplayChange?.(moduleDisplay);
        setTriggerFailed(false);
      } else {
        setTriggerFailed(true);
      }
    } catch {
      setTriggerFailed(true);
    } finally {
      setTriggerLoading(false);
    }
  };

  async function fetchPayload() {
    try {
      // Cancel previous in-flight request to prevent race conditions
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      abortControllerRef.current = new AbortController();

      const response = await authorizedFetch(buildCurrentDecisionUrl(siteId), {
        signal: abortControllerRef.current.signal,
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const json = await response.json();
      const data: DecisionPayload = json.data ?? json;
      setPayload(data);
      setError(null);
    } catch (err) {
      // Ignore abort errors (from race guard cancellation)
      if (err instanceof Error && err.name === "AbortError") {
        return;
      }
      const msg = err instanceof Error ? err.message : "Unknown error";
      setError(msg);
      // Keep stale payload if we have one — graceful degradation.
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    fetchPayload();

    timerRef.current = setInterval(() => {
      fetchPayload();
    }, POLL_INTERVAL_MS);

    return () => {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId]);

  // ── Derived values ────────────────────────────────────────────────────────

  const metadata = payload?.building_metadata ?? {};
  const floorStackOrder: string[] =
    (metadata.floor_stack_order ?? []).length > 0
      ? (metadata.floor_stack_order as string[])
      : DEFAULT_FLOOR_ORDER;
  const floorLabels: Record<string, string> = metadata.floor_labels ?? {};
  const activeIncidentMap: FloorStackProps["activeIncidentMap"] =
    payload?.active_incident_map ?? {};
  const rendererHint: "quiet" | "crisis" =
    payload?.renderer_hint === "crisis" ? "crisis" : "quiet";

  const equipmentCount: number | null = metadata.equipment_count ?? null;
  const activeRiskCount: number | null = metadata.active_risk_count ?? null;
  const healthPct: number | null = metadata.health_pct ?? null;

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div
      className="arcade-view"
      style={{
        position: "relative",
        background: "var(--color-sentinel-bg-panel, #0a0a0f)",
        border: "1px solid var(--color-sentinel-border, rgba(255,255,255,0.08))",
        borderRadius: 8,
        padding: 16,
        marginBottom: 16,
      }}
      data-renderer-hint={rendererHint}
      data-site-id={siteId}
    >
      {/* Header row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 12,
        }}
      >
        <span
          style={{
            fontSize: 12,
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            color: "var(--color-sentinel-text-secondary, #94a3b8)",
            fontFamily: "system-ui, sans-serif",
          }}
        >
          Building Spatial View
        </span>
        {error && !loading && (
          <span
            style={{
              fontSize: 11,
              color: "var(--color-sentinel-amber)",
              fontFamily: "system-ui, sans-serif",
            }}
            title={error}
          >
            Offline — using cached data
          </span>
        )}
      </div>

      {/* Summary strip */}
      <SummaryStrip
        equipmentCount={equipmentCount}
        activeRiskCount={activeRiskCount}
        healthPct={healthPct}
      />

      {/* Floor stack */}
      {loading && !payload ? (
        <SkeletonFloors count={floorStackOrder.length} />
      ) : (
        <FloorStack
          floorStackOrder={floorStackOrder}
          floorLabels={floorLabels}
          activeIncidentMap={activeIncidentMap}
          rendererHint={rendererHint}
          onFloorClick={handleFloorClick}
          selectedFloor={selectedFloor}
        />
      )}

      {/* ContextPanel — slides in from right on floor selection */}
      <ContextPanel
        open={contextOpen}
        floorId={selectedFloor}
        floorLabel={
          payload?.building_metadata?.floor_labels?.[selectedFloor ?? ""] ??
          selectedFloor ??
          ""
        }
        siteId={siteId}
        moduleDisplay={triggerModuleDisplay}
        triggerLoading={triggerLoading}
        triggerFailed={triggerFailed}
        floorIncident={
          selectedFloor && payload?.active_incident_map
            ? payload.active_incident_map[selectedFloor] ?? null
            : null
        }
        onClose={() => {
          setContextOpen(false);
          setSelectedFloor(null);
          setTriggerModuleDisplay({});
          setTriggerFailed(false);
          onModuleDisplayChange?.({});
        }}
      />
    </div>
  );
}
