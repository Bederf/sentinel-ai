import { buildCurrentDecisionUrl } from "@/lib/decisions";

/**
 * Kiosk Connection Manager — Phase 165.
 *
 * Primary:  SSE via EventSource — Jetson pushes DecisionMomentPayload on state change.
 *           Re-renders immediately. No polling overhead.
 *
 * Fallback: REST polling every 15s — activates automatically if SSE connection errors.
 *           Also activates if EventSource is unavailable (shouldn't happen in Chromium).
 *
 * Dismiss:  In-memory suppression of crisis re-trigger for dismiss_window_ms.
 *           Reboot caveat: dismissedUntil resets on Chromium restart (acceptable for
 *           wall-mounted kiosk — implement localStorage upgrade only if operators report it).
 */

const POLL_INTERVAL_MS = 15_000;
const SSE_RETRY_DELAY_MS = 5_000;   // Wait before re-attempting SSE after error
const DEFAULT_DISMISS_WINDOW_MS = 30 * 60 * 1000;

export type DecisionMomentPayload = {
  building_id: string;
  triggered_at: string;
  urgency_score: number;
  alert_text: string;
  reasoning_summary?: string;
  primary_asset_id: string | null;
  affected_zone_ids: string[];
  renderer_hint: "quiet" | "crisis";
  time_to_discomfort?: number | null;
  time_confidence?: string | number | null;
  estimated_impact?: unknown;
  active_posture?: string;
  posture_weights?: Record<string, number>;
  urgency_components?: Record<string, number>;
  building_metadata: {
    floors_count: number;
    floor_labels: Record<string, string>;
    floor_stack_order: string[];
    has_spatial_data: boolean;
    floor_stack: Array<{
      floor_id: string;
      floor_width_m: number;
      floor_depth_m: number;
      equipment_positions: Array<{ x: number; y: number; type: string }>;
    }>;
    deployment_mode: "ghost" | "advisory" | "supervised" | "autonomous";
  };
  active_incident_map: Record<string, { stack_index: number; svg_y_pct: number; affected: boolean }>;
  recommended_action: string;
  action_validation_state: string;
  requires_module: string | null;
  _connected?: boolean;   // sentinel value pushed on SSE connect — not a fault payload
  _offline?: boolean;     // service worker offline fallback
};

export type ConnectionControls = {
  stop: () => void;
  dismiss: (windowMs?: number) => void;
};

function getBuildingId(): string {
  const params = new URLSearchParams(window.location.search);
  const fromUrl = params.get("site") ?? params.get("building_id");
  if (fromUrl) return fromUrl;
  const meta = document.querySelector<HTMLMetaElement>('meta[name="building-id"]');
  if (meta?.content) return meta.content;
  const w = window as typeof window & { __KIOSK_CONFIG__?: { building_id?: string } };
  if (w.__KIOSK_CONFIG__?.building_id) return w.__KIOSK_CONFIG__.building_id;
  return "site-002";
}

export function startConnection(
  onUpdate: (payload: DecisionMomentPayload | null) => void,
): ConnectionControls {
  const buildingId = getBuildingId();
  let stopped = false;
  let dismissedUntil: number | null = null;
  let pollTimer: ReturnType<typeof setTimeout> | null = null;
  let sseSource: EventSource | null = null;
  let usingSSE = false;

  function isDismissed(): boolean {
    if (dismissedUntil === null) return false;
    if (Date.now() >= dismissedUntil) { dismissedUntil = null; return false; }
    return true;
  }

  function applyPayload(payload: DecisionMomentPayload): void {
    if (payload._connected) return; // SSE connect sentinel — not a real payload
    if (isDismissed() && payload.renderer_hint === "crisis") {
      onUpdate({ ...payload, renderer_hint: "quiet" });
    } else {
      onUpdate(payload);
    }
  }

  function dismiss(windowMs = DEFAULT_DISMISS_WINDOW_MS): void {
    dismissedUntil = Date.now() + windowMs;
    console.info(`[kiosk] dismissed until ${new Date(dismissedUntil).toLocaleTimeString()}`);
    onUpdate(null); // immediately render quiet
  }

  // ── SSE primary ─────────────────────────────────────────────────────────────

  function startSSE(): void {
    if (stopped) return;
    const url = `/api/decisions/stream/${encodeURIComponent(buildingId)}`;
    sseSource = new EventSource(url);
    usingSSE = true;

    sseSource.onmessage = (evt) => {
      try {
        const payload: DecisionMomentPayload = JSON.parse(evt.data);
        applyPayload(payload);
      } catch {
        console.warn("[kiosk] SSE parse error", evt.data);
      }
    };

    sseSource.onerror = () => {
      console.warn("[kiosk] SSE error — falling back to REST polling");
      sseSource?.close();
      sseSource = null;
      usingSSE = false;
      // Fall back to polling; retry SSE after delay
      startPolling();
      if (!stopped) setTimeout(retrySSE, SSE_RETRY_DELAY_MS * 6); // 30s before retry
    };
  }

  function retrySSE(): void {
    if (stopped || usingSSE) return;
    console.info("[kiosk] retrying SSE connection");
    stopPolling();
    startSSE();
  }

  // ── REST polling fallback ────────────────────────────────────────────────────

  async function poll(): Promise<void> {
    if (stopped || usingSSE) return;
    try {
      const res = await fetch(buildCurrentDecisionUrl(buildingId), {
        headers: { Accept: "application/json" },
      });
      if (res.status === 422) {
        onUpdate(null); // no active fault — quiet state
      } else if (res.ok) {
        const payload: DecisionMomentPayload = await res.json();
        applyPayload(payload);
      }
    } catch {
      // Network error — service worker returns cached/offline payload
      // Do not call onUpdate(null) here — keep last rendered state
    }
    if (!stopped && !usingSSE) {
      pollTimer = setTimeout(poll, POLL_INTERVAL_MS);
    }
  }

  function startPolling(): void {
    if (pollTimer) return;
    poll();
  }

  function stopPolling(): void {
    if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
  }

  // ── Init ─────────────────────────────────────────────────────────────────────

  if (typeof EventSource !== "undefined") {
    startSSE();
  } else {
    console.warn("[kiosk] EventSource not available — using REST polling only");
    startPolling();
  }

  return {
    stop: () => {
      stopped = true;
      sseSource?.close();
      stopPolling();
    },
    dismiss,
  };
}
