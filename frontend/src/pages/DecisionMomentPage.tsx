/**
 * DecisionMomentPage — Crisis State Full-page View (Phase 164)
 *
 * Renders a single-page decision context when urgency is elevated.
 * Sections: CAUSE, IMPACT, TIME, ACTION.
 */

import { useEffect, useState } from "react";
import { CheckCircle, AlertTriangle, XCircle, X } from "lucide-react";

import { UrgencyBar } from "../components/crisis/UrgencyBar";
import { AdvisoryModeGuide } from "../components/AdvisoryModeGuide";
import { buildDecisionSurface } from "../lib/decisionSurface";

export interface DecisionMomentPayload {
  building_id: string;
  triggered_at: string;
  trigger_reason: string;
  urgency_score: number;
  urgency_components: Record<string, number>;
  alert_text: string;
  primary_asset_id: string | null;
  affected_zone_ids: string[];
  affected_mesh_ids: string[];
  reasoning_summary: string;
  active_posture: string;
  posture_weights: Record<string, number>;
  time_to_discomfort: number | null;
  time_confidence: string | number | null;
  recommended_action: string;
  action_validation_state: string;
  requires_module: string | null;
  estimated_impact: string | Record<string, unknown>;
  building_metadata?: {
    deployment_mode?: "ghost" | "advisory" | "supervised" | "autonomous";
  };
}

interface DecisionMomentPageProps {
  payload: DecisionMomentPayload | null;
  onDismiss: () => void;
  siteId?: string;
}

function ActionValidationIcon({ state }: { state: string }) {
  if (state === "validated") {
    return <CheckCircle className="h-5 w-5" style={{ color: "var(--color-sentinel-green)" }} />;
  }
  if (state === "blocked") {
    return <XCircle className="h-5 w-5" style={{ color: "var(--color-sentinel-red)" }} />;
  }
  // unverified
  return <AlertTriangle className="h-5 w-5" style={{ color: "var(--color-sentinel-amber)" }} />;
}

function ZoneChips({ zoneIds }: { zoneIds: string[] }) {
  const MAX_SHOWN = 5;
  const shown = zoneIds.slice(0, MAX_SHOWN);
  const overflow = zoneIds.length - MAX_SHOWN;

  return (
    <div className="flex flex-wrap gap-1.5 mt-1">
      {shown.map((zone) => (
        <span
          key={zone}
          className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono"
          style={{
            background: "var(--color-sentinel-bg-secondary)",
            color: "var(--color-sentinel-text-secondary)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          {zone}
        </span>
      ))}
      {overflow > 0 && (
        <span
          className="inline-flex items-center px-2 py-0.5 rounded text-xs"
          style={{
            background: "var(--color-sentinel-bg-secondary)",
            color: "var(--color-sentinel-text-disabled)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          +{overflow} more
        </span>
      )}
    </div>
  );
}

export function DecisionMomentPage({ payload, onDismiss, siteId: _siteId }: DecisionMomentPageProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // Trigger fade-in on mount
    const t = setTimeout(() => setVisible(true), 10);
    return () => clearTimeout(t);
  }, []);

  if (!payload) {
    return (
      <div
        className="h-full flex items-center justify-center"
        style={{ background: "var(--color-sentinel-bg-canvas)" }}
      >
        <p style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading crisis context…</p>
      </div>
    );
  }

  const score = payload.urgency_score;
  const urgencyColor =
    score >= 0.8
      ? "var(--color-sentinel-red)"
      : score >= 0.6
        ? "var(--color-sentinel-amber)"
        : "var(--color-sentinel-blue)";
  const urgencyBorderColor =
    score >= 0.8
      ? "rgba(220, 38, 38, 0.4)"
      : score >= 0.6
        ? "rgba(245, 158, 11, 0.4)"
        : "rgba(59, 130, 246, 0.4)";

  const hasDefaultWeights =
    payload.reasoning_summary?.toLowerCase().includes("default weights");
  const surface = buildDecisionSurface(payload);

  return (
    <div
      className="h-full overflow-y-auto p-4 md:p-6"
      style={{
        background: "var(--color-sentinel-bg-canvas)",
        opacity: visible ? 1 : 0,
        transition: "opacity 0.3s ease-in",
      }}
    >
      <div className="max-w-4xl mx-auto flex flex-col gap-4">

        {/* Header row */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div
              className="w-2.5 h-2.5 rounded-full animate-pulse"
              style={{ background: urgencyColor }}
            />
            <span
              className="text-xs font-semibold uppercase tracking-widest"
              style={{ color: urgencyColor }}
            >
              Crisis View
            </span>
          </div>
          <button
            onClick={onDismiss}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs transition-colors hover:brightness-110"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-secondary)",
            }}
          >
            <X className="h-3.5 w-3.5" />
            Dismiss Crisis View
          </button>
        </div>

        {/* Default weights warning banner */}
        {hasDefaultWeights && (
          <div
            className="flex items-center gap-2 px-4 py-2.5 rounded"
            style={{
              background: "rgba(245, 158, 11, 0.12)",
              border: "1px solid rgba(245, 158, 11, 0.35)",
            }}
          >
            <AlertTriangle className="h-4 w-4 flex-shrink-0" style={{ color: "var(--color-sentinel-amber)" }} />
            <span className="text-sm" style={{ color: "var(--color-sentinel-amber)" }}>
              Building profile not configured — urgency scoring using defaults.
            </span>
          </div>
        )}

        {/* CAUSE */}
        <Card
          className="p-0 overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: `1px solid ${urgencyBorderColor}`,
          }}
        >
          <div
            className="px-4 py-2 text-xs font-semibold uppercase tracking-widest"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              borderBottom: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-disabled)",
            }}
          >
            Cause
          </div>
          <div className="px-4 py-4 flex flex-col gap-4">
            <p
              className="text-lg font-semibold leading-snug"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              {surface.cause}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              {payload.primary_asset_id && (
                <span
                  className="text-xs px-2 py-0.5 rounded font-mono"
                  style={{
                    background: "var(--color-sentinel-bg-secondary)",
                    color: "var(--color-sentinel-text-secondary)",
                    border: "1px solid var(--color-sentinel-border)",
                  }}
                >
                  {payload.primary_asset_id}
                </span>
              )}
              <span
                className="text-xs px-2 py-0.5 rounded"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  color: urgencyColor,
                  border: `1px solid ${urgencyBorderColor}`,
                }}
              >
                {surface.modeLabel} Mode
              </span>
            </div>
            <p className="text-sm leading-relaxed" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {payload.reasoning_summary}
            </p>
            {payload.affected_zone_ids.length > 0 && <ZoneChips zoneIds={payload.affected_zone_ids} />}
          </div>
        </Card>

        {/* IMPACT + TIME */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Impact */}
          <Card
            className="p-0 overflow-hidden"
            style={{
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <div
              className="px-4 py-2 text-xs font-semibold uppercase tracking-widest"
            style={{
                background: "var(--color-sentinel-bg-secondary)",
                borderBottom: "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-disabled)",
              }}
            >
              Impact
            </div>
            <div className="px-4 py-4 flex flex-col gap-4">
              <p className="text-sm leading-relaxed" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {surface.impact}
              </p>
              <p className="text-sm leading-relaxed" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {surface.action.tradeoff}
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-1.5">
                  <ActionValidationIcon state={payload.action_validation_state} />
                  <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    {payload.action_validation_state}
                  </span>
                </div>
                {payload.requires_module && (
                  <span
                    className="text-xs px-2 py-0.5 rounded"
                    style={{
                      background: "var(--color-sentinel-bg-secondary)",
                      color: "var(--color-sentinel-text-disabled)",
                      border: "1px solid var(--color-sentinel-border)",
                    }}
                  >
                    Requires: {payload.requires_module}
                  </span>
                )}
              </div>
              <UrgencyBar score={payload.urgency_score} />
            </div>
          </Card>

          {/* Time */}
          <Card
            className="p-0 overflow-hidden"
            style={{
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <div
              className="px-4 py-2 text-xs font-semibold uppercase tracking-widest"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                borderBottom: "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-disabled)",
              }}
            >
              Time
            </div>
            <div className="px-4 py-4 flex flex-col gap-3">
              <span
                className="text-xs font-semibold uppercase tracking-widest"
                style={{ color: urgencyColor }}
              >
                {surface.time.label}
              </span>
              <span
                className="text-3xl font-semibold tabular-nums"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                {surface.time.value}
              </span>
              <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {surface.time.detail}
              </span>
            </div>
          </Card>
        </div>

        {/* ACTION */}
        <Card
          className="p-0 overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div
            className="px-4 py-2 text-xs font-semibold uppercase tracking-widest"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              borderBottom: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-disabled)",
            }}
          >
            Action
          </div>
          <div className="px-4 py-4 flex flex-col gap-3">
            <div>
              <Button
                size="sm"
                color={score >= 0.8 ? "red" : score >= 0.6 ? "amber" : "blue"}
                variant="secondary"
              >
                {surface.action.summary}
              </Button>
            </div>
            <p className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
              {surface.action.operatorPrompt}
            </p>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {surface.action.expectedOutcome}
            </p>

            {surface.behavior.showInstructions && (
              <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                <AdvisoryModeGuide
                  bmsGuide={surface.action.bmsGuide}
                  _actionSummary={surface.action.summary}
                  primaryMetric={surface.time.label}
                />
              </div>
            )}

            {surface.behavior.showApproval && (
              <div
                className="rounded px-3 py-2 text-sm font-semibold"
                style={{
                  background: "rgba(245, 158, 11, 0.12)",
                  border: "1px solid rgba(245, 158, 11, 0.35)",
                  color: "var(--color-sentinel-amber)",
                }}
              >
                [HOLD TO APPROVE]
              </div>
            )}

            {surface.behavior.showResultOnly && (
              <div
                className="rounded px-3 py-2 text-sm"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  border: "1px solid var(--color-sentinel-border)",
                  color: "var(--color-sentinel-text-secondary)",
                }}
              >
                {surface.action.expectedOutcome}
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
