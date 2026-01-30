/**
 * ComfortComplaintPanel - Quick comfort complaint submission from dashboard
 *
 * Features:
 * - Desk ID input with auto-complete hints
 * - Complaint type selector (too hot, too cold, stuffy, drafty)
 * - Instant AI diagnosis display
 * - Confidence badge (high/medium/low)
 * - Actionable suggestions list
 *
 * Part of Phase 23: Desk-Level HVAC Intelligence
 */

import { useState, useRef, useEffect } from "react";
import { Card, Button, Badge, Callout } from "@tremor/react";
import {
  Thermometer,
  Send,
  RefreshCw,
  MapPin,
  Fan,
  AlertCircle,
  CheckCircle,
  XCircle,
  HelpCircle,
  MessageSquare,
} from "lucide-react";
import { complaintsApi, type ComplaintDiagnosis, type Desk, type HVACZone } from "../lib/api";

// Complaint type options with emojis
const COMPLAINT_TYPES = [
  { value: "too_hot", label: "Too Hot", icon: "fire" },
  { value: "too_cold", label: "Too Cold", icon: "snowflake" },
  { value: "stuffy", label: "Stuffy", icon: "cloud" },
  { value: "drafty", label: "Drafty", icon: "wind" },
] as const;

interface Props {
  compact?: boolean;
  onViewDetails?: () => void;
}

export default function ComfortComplaintPanel({ compact = true, onViewDetails }: Props) {
  // Form state
  const [deskId, setDeskId] = useState("");
  const [complaintType, setComplaintType] = useState<string>("too_hot");

  // API state
  const [diagnosis, setDiagnosis] = useState<ComplaintDiagnosis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Ref for auto-focus
  const deskInputRef = useRef<HTMLInputElement>(null);

  // Auto-focus desk input on load
  useEffect(() => {
    if (deskInputRef.current && !diagnosis) {
      deskInputRef.current.focus();
    }
  }, [diagnosis]);

  // Handle form submission
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!deskId.trim()) {
      setError("Please enter your desk ID");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const result = await complaintsApi.submitComplaint(deskId.trim(), complaintType);
      setDiagnosis(result);
    } catch (err) {
      console.error("Failed to submit complaint:", err);
      setError(err instanceof Error ? err.message : "Failed to submit complaint");
    } finally {
      setLoading(false);
    }
  };

  // Handle clear/reset
  const handleClear = () => {
    setDiagnosis(null);
    setDeskId("");
    setComplaintType("too_hot");
    setError(null);
  };

  // Get confidence badge color
  const getConfidenceBadgeColor = (confidence: string): "green" | "yellow" | "gray" => {
    switch (confidence) {
      case "high": return "green";
      case "medium": return "yellow";
      case "low": return "gray";
      default: return "gray";
    }
  };

  // Get icon for suggestion type
  const getSuggestionIcon = (suggestion: string) => {
    if (suggestion.toLowerCase().includes("auto") || suggestion.toLowerCase().includes("adjusted")) {
      return <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0" />;
    }
    if (suggestion.toLowerCase().includes("dispatch") || suggestion.toLowerCase().includes("ticket")) {
      return <AlertCircle className="w-4 h-4 text-amber-500 flex-shrink-0" />;
    }
    return <HelpCircle className="w-4 h-4 text-blue-500 flex-shrink-0" />;
  };

  // Render desk info card
  const renderDeskInfo = (desk: Desk) => (
    <div
      className="p-3 rounded-lg"
      style={{ background: "var(--color-sentinel-bg-secondary)" }}
    >
      <div className="flex items-center gap-2 mb-2">
        <MapPin className="w-4 h-4" style={{ color: "var(--color-sentinel-blue)" }} />
        <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
          {desk.desk_id}
        </span>
      </div>
      <div className="text-xs space-y-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
        <div>{desk.floor} - {desk.building}</div>
        <div className="flex flex-wrap gap-2">
          {desk.near_window && (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs"
                  style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--color-sentinel-amber)" }}>
              Near Window
            </span>
          )}
          {desk.near_diffuser && (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs"
                  style={{ background: "rgba(59, 130, 246, 0.15)", color: "var(--color-sentinel-blue)" }}>
              Near Diffuser
            </span>
          )}
          {desk.near_printer && (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs"
                  style={{ background: "rgba(239, 68, 68, 0.15)", color: "var(--color-sentinel-red)" }}>
              Near Printer
            </span>
          )}
        </div>
      </div>
    </div>
  );

  // Render zone status card
  const renderZoneStatus = (zone: HVACZone) => (
    <div
      className="p-3 rounded-lg"
      style={{ background: "var(--color-sentinel-bg-secondary)" }}
    >
      <div className="flex items-center gap-2 mb-2">
        <Fan className="w-4 h-4" style={{ color: "var(--color-sentinel-green)" }} />
        <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
          {zone.zone_name}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Temp: </span>
          <span style={{ color: "var(--color-sentinel-text-primary)" }}>{zone.current_temp}C</span>
        </div>
        <div>
          <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Setpoint: </span>
          <span style={{ color: "var(--color-sentinel-text-primary)" }}>{zone.setpoint}C</span>
        </div>
        <div>
          <span style={{ color: "var(--color-sentinel-text-secondary)" }}>FCU: </span>
          <span style={{ color: "var(--color-sentinel-text-primary)" }}>{zone.fcu_id}</span>
        </div>
        <div>
          <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Status: </span>
          <span style={{
            color: zone.status === "running" ? "var(--color-sentinel-green)" :
                   zone.status === "fault" ? "var(--color-sentinel-red)" :
                   "var(--color-sentinel-amber)"
          }}>
            {zone.status}
          </span>
        </div>
      </div>
    </div>
  );

  // Render diagnosis result
  const renderDiagnosis = () => {
    if (!diagnosis) return null;

    return (
      <div className="space-y-4 mt-4">
        {/* Desk and Zone Info */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {renderDeskInfo(diagnosis.desk)}
          {renderZoneStatus(diagnosis.zone)}
        </div>

        {/* Root Cause with Confidence */}
        <div
          className="p-4 rounded-lg"
          style={{
            background: "var(--color-sentinel-bg-secondary)",
            borderLeft: `4px solid ${
              diagnosis.confidence === "high" ? "var(--color-sentinel-green)" :
              diagnosis.confidence === "medium" ? "var(--color-sentinel-amber)" :
              "var(--color-sentinel-text-disabled)"
            }`
          }}
        >
          <div className="flex items-start justify-between gap-4 mb-2">
            <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
              Diagnosis
            </span>
            <Badge color={getConfidenceBadgeColor(diagnosis.confidence)} size="sm">
              {diagnosis.confidence} confidence
            </Badge>
          </div>
          <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            {diagnosis.root_cause}
          </p>
        </div>

        {/* Suggestions */}
        <div className="space-y-2">
          <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Recommendations
          </span>
          <div className="space-y-2">
            {diagnosis.suggestions.map((suggestion, index) => (
              <div
                key={index}
                className="flex items-start gap-2 p-2 rounded"
                style={{ background: "var(--color-sentinel-bg-secondary)" }}
              >
                {getSuggestionIcon(suggestion)}
                <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {suggestion}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Dispatch Alert */}
        {diagnosis.needs_dispatch && (
          <Callout title="Technician Required" color="amber">
            This issue requires a technician visit. A work order has been created.
          </Callout>
        )}

        {/* Auto Action */}
        {diagnosis.auto_action_taken && (
          <Callout title="Auto Action Taken" color="green">
            {diagnosis.auto_action_taken}
          </Callout>
        )}

        {/* Action Buttons */}
        <div className="flex items-center gap-3 pt-2">
          <Button size="xs" variant="secondary" onClick={handleClear} icon={RefreshCw}>
            Submit Another
          </Button>
          {onViewDetails && (
            <Button size="xs" variant="primary" onClick={onViewDetails} icon={MessageSquare}>
              Need More Help?
            </Button>
          )}
        </div>
      </div>
    );
  };

  // Render complaint form
  const renderForm = () => (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className={compact ? "flex flex-col sm:flex-row gap-3" : "space-y-4"}>
        {/* Desk ID Input */}
        <div className={compact ? "flex-grow" : ""}>
          <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Desk ID
          </label>
          <input
            ref={deskInputRef}
            type="text"
            value={deskId}
            onChange={(e) => setDeskId(e.target.value)}
            placeholder="e.g., 25, L12-25"
            className="w-full px-3 py-2 rounded-md text-sm"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          />
        </div>

        {/* Complaint Type Selector */}
        <div className={compact ? "flex-shrink-0" : ""}>
          <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Issue
          </label>
          <select
            value={complaintType}
            onChange={(e) => setComplaintType(e.target.value)}
            className="w-full px-3 py-2 rounded-md text-sm"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          >
            {COMPLAINT_TYPES.map((type) => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </select>
        </div>

        {/* Submit Button */}
        <div className={compact ? "flex items-end" : ""}>
          <Button
            type="submit"
            size="sm"
            variant="primary"
            disabled={loading || !deskId.trim()}
            icon={loading ? RefreshCw : Send}
            className={loading ? "animate-spin" : ""}
          >
            {loading ? "Analyzing..." : "Submit"}
          </Button>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <Callout title="Error" color="red" icon={XCircle}>
          {error}
        </Callout>
      )}
    </form>
  );

  return (
    <Card
      className="overflow-hidden"
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
          <div
            className="p-2 rounded"
            style={{ background: "rgba(245, 158, 11, 0.15)" }}
          >
            <Thermometer
              className="h-5 w-5"
              style={{ color: "var(--color-sentinel-amber)" }}
            />
          </div>
          <div>
            <h3
              className="font-medium text-sm"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Comfort Assistant
            </h3>
            <span
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              Too hot? Too cold? We can help!
            </span>
          </div>
        </div>

        {diagnosis && (
          <Badge color={getConfidenceBadgeColor(diagnosis.confidence)}>
            Diagnosed
          </Badge>
        )}
      </div>

      {/* Panel Content */}
      <div className="p-4">
        {diagnosis ? renderDiagnosis() : renderForm()}
      </div>
    </Card>
  );
}
