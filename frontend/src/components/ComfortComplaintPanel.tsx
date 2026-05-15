import { useState, useRef, useEffect } from "react";

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
import { complaintsApi, type ComplaintDiagnosis, type Desk, type HVACZone } from '@/lib/api';
import { Badge } from './Badge';

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
  const [deskId, setDeskId] = useState("");
  const [complaintType, setComplaintType] = useState<string>("too_hot");

  const [diagnosis, setDiagnosis] = useState<ComplaintDiagnosis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const deskInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (deskInputRef.current && !diagnosis) {
      deskInputRef.current.focus();
    }
  }, [diagnosis]);

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

  const handleClear = () => {
    setDiagnosis(null);
    setDeskId("");
    setComplaintType("too_hot");
    setError(null);
  };

  const getConfidenceBadgeStyle = (confidence: string) => {
    switch (confidence) {
      case "high": return { background: 'rgba(16,185,129,0.15)', color: 'var(--color-sentinel-green)' };
      case "medium": return { background: 'rgba(234,179,8,0.15)', color: 'var(--color-sentinel-amber)' };
      case "low": return { background: 'rgba(107,114,128,0.15)', color: 'var(--color-sentinel-text-secondary)' };
      default: return { background: 'rgba(107,114,128,0.15)', color: 'var(--color-sentinel-text-secondary)' };
    }
  };

  const getSuggestionIcon = (suggestion: string) => {
    if (suggestion.toLowerCase().includes("auto") || suggestion.toLowerCase().includes("adjusted")) {
      return <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0" />;
    }
    if (suggestion.toLowerCase().includes("dispatch") || suggestion.toLowerCase().includes("ticket")) {
      return <AlertCircle className="w-4 h-4 text-amber-500 flex-shrink-0" />;
    }
    return <HelpCircle className="w-4 h-4 text-blue-500 flex-shrink-0" />;
  };

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

  const renderCallout = (title: string, color: 'amber' | 'green' | 'red', icon?: React.ReactNode, children?: React.ReactNode) => {
    const borderColor = color === 'amber' ? '#f59e0b' : color === 'green' ? '#22c55e' : '#ef4444';
    const bgColor = color === 'amber' ? 'rgba(245,158,11,0.12)' : color === 'green' ? 'rgba(16,185,129,0.12)' : 'rgba(239,68,68,0.12)';
    return (
      <div className="p-3 rounded-lg flex items-start gap-2" style={{ background: bgColor, borderLeft: `4px solid ${borderColor}` }}>
        {icon && <span className="flex-shrink-0 mt-0.5">{icon}</span>}
        <div>
          <p className="text-sm font-medium" style={{ color: 'var(--color-sentinel-text-primary)' }}>{title}</p>
          <div className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>{children}</div>
        </div>
      </div>
    );
  };

  const renderDiagnosis = () => {
    if (!diagnosis) return null;

    return (
      <div className="space-y-4 mt-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {renderDeskInfo(diagnosis.desk)}
          {renderZoneStatus(diagnosis.zone)}
        </div>

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
            <Badge style={getConfidenceBadgeStyle(diagnosis.confidence)}>
              {diagnosis.confidence} confidence
            </Badge>
          </div>
          <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            {diagnosis.root_cause}
          </p>
        </div>

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

        {diagnosis.needs_dispatch && (
          renderCallout("Technician Required", "amber", undefined,
            <>This issue requires a technician visit. A work order has been created.</>
          )
        )}

        {diagnosis.auto_action_taken && (
          renderCallout("Auto Action Taken", "green", undefined,
            <>{diagnosis.auto_action_taken}</>
          )
        )}

        <div className="flex items-center gap-3 pt-2">
          <button
            onClick={handleClear}
            className="px-2 py-1 text-xs rounded font-medium inline-flex items-center gap-1"
            style={{
              background: 'var(--color-sentinel-bg-secondary)',
              color: 'var(--color-sentinel-text-primary)',
              border: '1px solid var(--color-sentinel-border)',
            }}
          >
            <RefreshCw className="w-3 h-3" />
            Submit Another
          </button>
          {onViewDetails && (
            <button
              onClick={onViewDetails}
              className="px-2 py-1 text-xs rounded font-medium inline-flex items-center gap-1"
              style={{
                background: 'var(--color-sentinel-bg-secondary)',
                color: 'var(--color-sentinel-text-primary)',
                border: '1px solid var(--color-sentinel-border)',
              }}
            >
              <MessageSquare className="w-3 h-3" />
              Need More Help?
            </button>
          )}
        </div>
      </div>
    );
  };

  const renderForm = () => (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className={compact ? "flex flex-col sm:flex-row gap-3" : "space-y-4"}>
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

        <div className={compact ? "flex items-end" : ""}>
          <button
            type="submit"
            disabled={loading || !deskId.trim()}
            className={`px-3 py-2 text-sm rounded font-medium inline-flex items-center gap-1 ${loading ? "animate-spin" : ""}`}
            style={{
              background: 'rgba(59,130,246,0.15)',
              color: 'var(--color-sentinel-blue)',
              border: '1px solid rgba(59,130,246,0.3)',
              opacity: loading || !deskId.trim() ? 0.6 : 1,
            }}
          >
            {loading ? <RefreshCw className="w-3.5 h-3.5" /> : <Send className="w-3.5 h-3.5" />}
            {loading ? "Analyzing..." : "Submit"}
          </button>
        </div>
      </div>

      {error && (
        renderCallout("Error", "red", <XCircle className="w-4 h-4" />, <>{error}</>)
      )}
    </form>
  );

  return (
    <div
      className="rounded-md overflow-hidden"
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
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
          <Badge style={getConfidenceBadgeStyle(diagnosis.confidence)}>
            Diagnosed
          </Badge>
        )}
      </div>

      <div className="p-4">
        {diagnosis ? renderDiagnosis() : renderForm()}
      </div>
    </div>
  );
}
