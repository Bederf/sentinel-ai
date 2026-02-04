import { useReducer, useCallback } from "react";
import {
  CheckCircle,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Loader2,
  Wifi,
  Search,
  ClipboardCheck,
  ShieldCheck,
} from "lucide-react";
import type {
  Site,
  NiagaraMappingSummary,
  DiscoverClassifyResponse,
  BMSVendor,
} from "../lib/api";
import { niagaraApi } from "../lib/api";

// ============= BMS Vendor Definitions =============

const BMS_VENDORS = [
  { value: "niagara" as const, label: "Tridium Niagara 4", protocol: "oBIX + BACnet/IP" },
  { value: "desigo" as const, label: "Siemens Desigo CC", protocol: "BACnet/IP" },
  { value: "metasys" as const, label: "Johnson Controls Metasys", protocol: "BACnet/IP" },
  { value: "honeywell" as const, label: "Honeywell EBI", protocol: "BACnet/IP" },
  { value: "schneider" as const, label: "Schneider EcoStruxure", protocol: "BACnet/IP" },
  { value: "trend" as const, label: "Trend Controls IQ4", protocol: "BACnet/IP" },
  { value: "generic" as const, label: "Generic BACnet/IP", protocol: "BACnet/IP" },
];

// ============= Types =============

export interface BMSConnectionWizardProps {
  siteId: string;
  sites: Site[];
  onClose: () => void;
  onComplete: () => void;
}

type ConnectionStatus = "idle" | "testing" | "connected" | "failed";
type ApproveStatus = "idle" | "approving" | "approved" | "failed";

interface WizardState {
  step: number;
  bmsVendor: BMSVendor;
  host: string;
  port: number;
  username: string;
  password: string;
  useHttps: boolean;
  useDemoData: boolean;
  siteId: string;
  connectionStatus: ConnectionStatus;
  connectionMessage: string;
  discoveryId: string | null;
  discoverySummary: DiscoverClassifyResponse | null;
  mappings: NiagaraMappingSummary | null;
  expandedEquipment: Set<string>;
  approvedBy: string;
  approveStatus: ApproveStatus;
  approveMessage: string;
  approveResult: { equipment_created: number } | null;
  loading: boolean;
  error: string | null;
}

type WizardAction =
  | { type: "SET_FIELD"; field: string; value: string | number | boolean }
  | { type: "SET_CONNECTION_STATUS"; status: ConnectionStatus; message?: string }
  | { type: "SET_STEP"; step: number }
  | { type: "SET_DISCOVERY"; id: string; summary: DiscoverClassifyResponse }
  | { type: "SET_MAPPINGS"; mappings: NiagaraMappingSummary }
  | { type: "TOGGLE_EQUIPMENT"; equipmentId: string }
  | { type: "SET_APPROVE_STATUS"; status: ApproveStatus; message?: string; result?: { equipment_created: number } }
  | { type: "SET_LOADING"; loading: boolean }
  | { type: "SET_ERROR"; error: string | null };

function wizardReducer(state: WizardState, action: WizardAction): WizardState {
  switch (action.type) {
    case "SET_FIELD":
      return { ...state, [action.field]: action.value };
    case "SET_CONNECTION_STATUS":
      return {
        ...state,
        connectionStatus: action.status,
        connectionMessage: action.message || "",
      };
    case "SET_STEP":
      return { ...state, step: action.step, error: null };
    case "SET_DISCOVERY":
      return {
        ...state,
        discoveryId: action.id,
        discoverySummary: action.summary,
        loading: false,
      };
    case "SET_MAPPINGS":
      return { ...state, mappings: action.mappings, loading: false };
    case "TOGGLE_EQUIPMENT": {
      const next = new Set(state.expandedEquipment);
      if (next.has(action.equipmentId)) {
        next.delete(action.equipmentId);
      } else {
        next.add(action.equipmentId);
      }
      return { ...state, expandedEquipment: next };
    }
    case "SET_APPROVE_STATUS":
      return {
        ...state,
        approveStatus: action.status,
        approveMessage: action.message || "",
        approveResult: action.result || state.approveResult,
        loading: action.status === "approving",
      };
    case "SET_LOADING":
      return { ...state, loading: action.loading };
    case "SET_ERROR":
      return { ...state, error: action.error, loading: false };
    default:
      return state;
  }
}

// ============= Sub-components =============

function StepIndicator({ currentStep }: { currentStep: number }) {
  const steps = [
    { num: 1, label: "Connect", icon: Wifi },
    { num: 2, label: "Discover", icon: Search },
    { num: 3, label: "Review", icon: ClipboardCheck },
    { num: 4, label: "Approve", icon: ShieldCheck },
  ];

  return (
    <div className="flex items-center justify-center gap-0 mb-8">
      {steps.map((s, i) => {
        const Icon = s.icon;
        const isCompleted = currentStep > s.num;
        const isActive = currentStep === s.num;
        const isPending = currentStep < s.num;

        return (
          <div key={s.num} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                className="w-10 h-10 rounded-full flex items-center justify-center text-sm font-semibold transition-colors"
                style={{
                  background: isCompleted
                    ? "var(--color-sentinel-green)"
                    : isActive
                      ? "var(--color-sentinel-blue)"
                      : "var(--color-sentinel-bg-secondary)",
                  color: isPending
                    ? "var(--color-sentinel-text-secondary)"
                    : "#fff",
                  border: isPending
                    ? "1px solid var(--color-sentinel-border)"
                    : "none",
                }}
              >
                {isCompleted ? (
                  <CheckCircle className="w-5 h-5" />
                ) : (
                  <Icon className="w-5 h-5" />
                )}
              </div>
              <span
                className="text-xs mt-1 font-medium"
                style={{
                  color: isActive
                    ? "var(--color-sentinel-blue)"
                    : isCompleted
                      ? "var(--color-sentinel-green)"
                      : "var(--color-sentinel-text-secondary)",
                }}
              >
                {s.label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div
                className="w-16 h-0.5 mx-2 mt-[-16px]"
                style={{
                  background:
                    currentStep > s.num
                      ? "var(--color-sentinel-green)"
                      : "var(--color-sentinel-border)",
                }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

function ConfidenceBadge({ confidence }: { confidence: string }) {
  const colorMap: Record<string, string> = {
    high: "var(--color-sentinel-green)",
    medium: "var(--color-sentinel-amber)",
    low: "var(--color-sentinel-red)",
  };
  const bg = colorMap[confidence] || "var(--color-sentinel-text-secondary)";

  return (
    <span
      className="text-xs px-2 py-0.5 rounded-full font-medium"
      style={{ background: `${bg}22`, color: bg, border: `1px solid ${bg}44` }}
    >
      {confidence}
    </span>
  );
}

// ============= Input helpers =============

const inputStyle: React.CSSProperties = {
  background: "var(--color-sentinel-bg-secondary)",
  border: "1px solid var(--color-sentinel-border)",
  color: "var(--color-sentinel-text-primary)",
};

const labelStyle: React.CSSProperties = {
  color: "var(--color-sentinel-text-secondary)",
};

// ============= Main Component =============

export function BMSConnectionWizard({
  siteId: initialSiteId,
  sites,
  onClose,
  onComplete,
}: BMSConnectionWizardProps) {
  const [state, dispatch] = useReducer(wizardReducer, {
    step: 1,
    bmsVendor: "niagara",
    host: "",
    port: 80,
    username: "",
    password: "",
    useHttps: false,
    useDemoData: false,
    siteId: initialSiteId || (sites.length > 0 ? sites[0].id : ""),
    connectionStatus: "idle",
    connectionMessage: "",
    discoveryId: null,
    discoverySummary: null,
    mappings: null,
    expandedEquipment: new Set<string>(),
    approvedBy: "system",
    approveStatus: "idle",
    approveMessage: "",
    approveResult: null,
    loading: false,
    error: null,
  });

  const isNiagara = state.bmsVendor === "niagara";
  const vendorLabel = BMS_VENDORS.find((v) => v.value === state.bmsVendor)?.label ?? state.bmsVendor;

  // ---------- Step 1: Test Connection ----------
  const handleTestConnection = useCallback(async () => {
    dispatch({ type: "SET_CONNECTION_STATUS", status: "testing" });
    dispatch({ type: "SET_ERROR", error: null });

    if (state.useDemoData) {
      dispatch({
        type: "SET_CONNECTION_STATUS",
        status: "connected",
        message: "Demo mode — using pre-seeded discovery data",
      });
      return;
    }

    try {
      if (state.bmsVendor === 'niagara') {
        // oBIX connection test (existing flow)
        const res = await niagaraApi.configureOBIX({
          host: state.host,
          port: state.port,
          username: state.username,
          password: state.password,
          use_https: state.useHttps,
          timeout: 10,
        });
        dispatch({
          type: "SET_CONNECTION_STATUS",
          status: res.connected ? "connected" : "failed",
          message: res.message,
        });
      } else {
        // BACnet WhoIs test (new flow for non-Niagara vendors)
        const res = await niagaraApi.testBACnetConnection({ timeout: 5 });
        if (res.count > 0) {
          const deviceNames = res.devices
            .map((d) => d.object_name || `Device ${d.device_id}`)
            .join(", ");
          dispatch({
            type: "SET_CONNECTION_STATUS",
            status: "connected",
            message: `Found ${res.count} BACnet device(s): ${deviceNames}`,
          });
        } else {
          dispatch({
            type: "SET_CONNECTION_STATUS",
            status: "failed",
            message:
              "No BACnet devices found on the network. Check network connectivity and BACnet port (47808).",
          });
        }
      }
    } catch (err) {
      dispatch({
        type: "SET_CONNECTION_STATUS",
        status: "failed",
        message: err instanceof Error ? err.message : "Connection failed",
      });
    }
  }, [state.bmsVendor, state.host, state.port, state.username, state.password, state.useHttps, state.useDemoData]);

  // ---------- Step 2: Discover & Classify ----------
  const handleDiscover = useCallback(async () => {
    dispatch({ type: "SET_LOADING", loading: true });
    dispatch({ type: "SET_ERROR", error: null });

    try {
      const res = await niagaraApi.discoverAndClassify({
        device_ip: state.useDemoData ? "demo" : state.host,
        site_id: state.siteId,
        use_demo: state.useDemoData,
        bms_vendor: state.bmsVendor,
      });
      dispatch({ type: "SET_DISCOVERY", id: res.discovery_id, summary: res });
    } catch (err) {
      dispatch({
        type: "SET_ERROR",
        error: err instanceof Error ? err.message : "Discovery failed",
      });
    }
  }, [state.host, state.siteId, state.useDemoData, state.bmsVendor]);

  // ---------- Step 3: Load Mappings ----------
  const handleLoadMappings = useCallback(async () => {
    if (!state.discoveryId) return;
    dispatch({ type: "SET_LOADING", loading: true });
    dispatch({ type: "SET_ERROR", error: null });

    try {
      const res = await niagaraApi.getMappings(state.discoveryId);
      dispatch({ type: "SET_MAPPINGS", mappings: res });
    } catch (err) {
      dispatch({
        type: "SET_ERROR",
        error: err instanceof Error ? err.message : "Failed to load mappings",
      });
    }
  }, [state.discoveryId]);

  // ---------- Step 4: Approve ----------
  const handleApprove = useCallback(async () => {
    if (!state.discoveryId) return;
    dispatch({ type: "SET_APPROVE_STATUS", status: "approving" });

    try {
      const res = await niagaraApi.approveMappings(
        state.discoveryId,
        state.approvedBy,
      );
      dispatch({
        type: "SET_APPROVE_STATUS",
        status: res.success ? "approved" : "failed",
        message: res.message,
        result: { equipment_created: res.equipment_created },
      });
    } catch (err) {
      dispatch({
        type: "SET_APPROVE_STATUS",
        status: "failed",
        message: err instanceof Error ? err.message : "Approval failed",
      });
    }
  }, [state.discoveryId, state.approvedBy]);

  // ---------- Step navigation ----------
  const goNext = useCallback(async () => {
    const nextStep = state.step + 1;
    dispatch({ type: "SET_STEP", step: nextStep });

    if (nextStep === 2) {
      await handleDiscover();
    } else if (nextStep === 3) {
      await handleLoadMappings();
    }
  }, [state.step, handleDiscover, handleLoadMappings]);

  const goBack = useCallback(() => {
    dispatch({ type: "SET_STEP", step: Math.max(1, state.step - 1) });
  }, [state.step]);

  const canGoNext = (): boolean => {
    switch (state.step) {
      case 1:
        return state.connectionStatus === "connected" && !!state.siteId;
      case 2:
        return !!state.discoveryId && !state.loading;
      case 3:
        return !!state.mappings && !state.loading;
      default:
        return false;
    }
  };

  // ============= Render Steps =============

  const renderStep1 = () => (
    <div className="space-y-5">
      <div>
        <h3
          className="text-lg font-semibold mb-1"
          style={{ color: "var(--color-sentinel-text-primary)" }}
        >
          Connect to BMS
        </h3>
        <p
          className="text-sm"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          Select your BMS vendor and configure connection details. SENTINEL will discover and classify your building automation points.
        </p>
      </div>

      {/* BMS Vendor selector */}
      <div>
        <label className="block text-sm font-medium mb-1" style={labelStyle}>
          BMS Vendor
        </label>
        <select
          value={state.bmsVendor}
          onChange={(e) => {
            dispatch({
              type: "SET_FIELD",
              field: "bmsVendor",
              value: e.target.value,
            });
            // Reset connection status when vendor changes
            dispatch({ type: "SET_CONNECTION_STATUS", status: "idle" });
          }}
          className="w-full rounded px-3 py-2 text-sm"
          style={inputStyle}
        >
          {BMS_VENDORS.map((v) => (
            <option key={v.value} value={v.value}>
              {v.label} ({v.protocol})
            </option>
          ))}
        </select>
      </div>

      {/* Demo toggle */}
      <label
        className="flex items-center gap-3 p-3 rounded cursor-pointer"
        style={{
          background: state.useDemoData
            ? "var(--color-sentinel-blue)11"
            : "var(--color-sentinel-bg-secondary)",
          border: `1px solid ${state.useDemoData ? "var(--color-sentinel-blue)" : "var(--color-sentinel-border)"}`,
        }}
      >
        <input
          type="checkbox"
          checked={state.useDemoData}
          onChange={(e) =>
            dispatch({
              type: "SET_FIELD",
              field: "useDemoData",
              value: e.target.checked,
            })
          }
          className="w-4 h-4"
        />
        <div>
          <span
            className="text-sm font-medium"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            Use Demo Data
          </span>
          <p
            className="text-xs mt-0.5"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            Skip real connection and use pre-seeded Sandton City discovery data
          </p>
        </div>
      </label>

      {/* Site selector */}
      <div>
        <label className="block text-sm font-medium mb-1" style={labelStyle}>
          Target Site
        </label>
        <select
          value={state.siteId}
          onChange={(e) =>
            dispatch({
              type: "SET_FIELD",
              field: "siteId",
              value: e.target.value,
            })
          }
          className="w-full rounded px-3 py-2 text-sm"
          style={inputStyle}
        >
          {sites.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </div>

      {/* Connection fields — hidden in demo mode */}
      {!state.useDemoData && isNiagara && (
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2 sm:col-span-1">
            <label
              className="block text-sm font-medium mb-1"
              style={labelStyle}
            >
              Host / IP Address
            </label>
            <input
              type="text"
              value={state.host}
              onChange={(e) =>
                dispatch({
                  type: "SET_FIELD",
                  field: "host",
                  value: e.target.value,
                })
              }
              placeholder="192.168.1.100"
              className="w-full rounded px-3 py-2 text-sm"
              style={inputStyle}
            />
          </div>
          <div className="col-span-2 sm:col-span-1">
            <label
              className="block text-sm font-medium mb-1"
              style={labelStyle}
            >
              Port
            </label>
            <input
              type="number"
              value={state.port}
              onChange={(e) =>
                dispatch({
                  type: "SET_FIELD",
                  field: "port",
                  value: parseInt(e.target.value, 10) || 80,
                })
              }
              className="w-full rounded px-3 py-2 text-sm"
              style={inputStyle}
            />
          </div>
          <div className="col-span-2 sm:col-span-1">
            <label
              className="block text-sm font-medium mb-1"
              style={labelStyle}
            >
              Username
            </label>
            <input
              type="text"
              value={state.username}
              onChange={(e) =>
                dispatch({
                  type: "SET_FIELD",
                  field: "username",
                  value: e.target.value,
                })
              }
              placeholder="admin"
              className="w-full rounded px-3 py-2 text-sm"
              style={inputStyle}
            />
          </div>
          <div className="col-span-2 sm:col-span-1">
            <label
              className="block text-sm font-medium mb-1"
              style={labelStyle}
            >
              Password
            </label>
            <input
              type="password"
              value={state.password}
              onChange={(e) =>
                dispatch({
                  type: "SET_FIELD",
                  field: "password",
                  value: e.target.value,
                })
              }
              className="w-full rounded px-3 py-2 text-sm"
              style={inputStyle}
            />
          </div>
          <div className="col-span-2">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={state.useHttps}
                onChange={(e) =>
                  dispatch({
                    type: "SET_FIELD",
                    field: "useHttps",
                    value: e.target.checked,
                  })
                }
                className="w-4 h-4"
              />
              <span
                className="text-sm"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Use HTTPS
              </span>
            </label>
          </div>
        </div>
      )}

      {/* BACnet-only info for non-Niagara vendors (not in demo mode) */}
      {!state.useDemoData && !isNiagara && (
        <div
          className="p-3 rounded text-sm"
          style={{
            background: "var(--color-sentinel-bg-secondary)",
            border: "1px solid var(--color-sentinel-border)",
            color: "var(--color-sentinel-text-secondary)",
          }}
        >
          No credentials required. SENTINEL will broadcast a BACnet WhoIs on the local network (UDP port 47808) to discover {vendorLabel} controllers.
        </div>
      )}

      {/* Test connection button */}
      <button
        onClick={handleTestConnection}
        disabled={
          state.connectionStatus === "testing" ||
          (!state.useDemoData && isNiagara && !state.host)
        }
        className="flex items-center gap-2 px-4 py-2 rounded text-sm font-medium transition-opacity disabled:opacity-50"
        style={{
          background: "var(--color-sentinel-blue)",
          color: "#fff",
        }}
      >
        {state.connectionStatus === "testing" ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Wifi className="w-4 h-4" />
        )}
        {state.useDemoData ? "Enable Demo Mode" : "Test Connection"}
      </button>

      {/* Connection result */}
      {state.connectionStatus === "connected" && (
        <div
          className="flex items-start gap-2 p-3 rounded text-sm"
          style={{
            background: "var(--color-sentinel-green)11",
            border: "1px solid var(--color-sentinel-green)",
            color: "var(--color-sentinel-green)",
          }}
        >
          <CheckCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>{state.connectionMessage}</span>
        </div>
      )}
      {state.connectionStatus === "failed" && (
        <div
          className="flex items-start gap-2 p-3 rounded text-sm"
          style={{
            background: "var(--color-sentinel-red)11",
            border: "1px solid var(--color-sentinel-red)",
            color: "var(--color-sentinel-red)",
          }}
        >
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>{state.connectionMessage}</span>
        </div>
      )}
    </div>
  );

  const renderStep2 = () => (
    <div className="space-y-5">
      <div>
        <h3
          className="text-lg font-semibold mb-1"
          style={{ color: "var(--color-sentinel-text-primary)" }}
        >
          Discover &amp; Classify Points
        </h3>
        <p
          className="text-sm"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          AI is scanning BACnet points and classifying them into equipment
          groups using Brick Schema ontology.
        </p>
      </div>

      {state.loading && (
        <div className="flex flex-col items-center gap-3 py-8">
          <Loader2
            className="w-10 h-10 animate-spin"
            style={{ color: "var(--color-sentinel-blue)" }}
          />
          <p
            className="text-sm"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            Discovering and classifying BACnet points...
          </p>
        </div>
      )}

      {state.error && (
        <div
          className="flex items-start gap-2 p-3 rounded text-sm"
          style={{
            background: "var(--color-sentinel-red)11",
            border: "1px solid var(--color-sentinel-red)",
            color: "var(--color-sentinel-red)",
          }}
        >
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <div>
            <p>{state.error}</p>
            <button
              onClick={handleDiscover}
              className="mt-2 underline text-xs"
            >
              Retry discovery
            </button>
          </div>
        </div>
      )}

      {state.discoverySummary && !state.loading && (
        <div className="space-y-4">
          <div
            className="flex items-start gap-2 p-3 rounded text-sm"
            style={{
              background: "var(--color-sentinel-green)11",
              border: "1px solid var(--color-sentinel-green)",
              color: "var(--color-sentinel-green)",
            }}
          >
            <CheckCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>
              Discovery complete — {state.discoverySummary.points_count} points
              found, {state.discoverySummary.equipment_count} equipment groups
              classified
            </span>
          </div>

          {/* Summary cards */}
          <div className="grid grid-cols-3 gap-3">
            <SummaryCard
              label="Points Found"
              value={state.discoverySummary.points_count}
              color="var(--color-sentinel-blue)"
            />
            <SummaryCard
              label="Equipment Groups"
              value={state.discoverySummary.equipment_count}
              color="var(--color-sentinel-green)"
            />
            <SummaryCard
              label="Status"
              value={state.discoverySummary.status}
              color="var(--color-sentinel-amber)"
            />
          </div>

          {/* Classification summary */}
          {state.discoverySummary.summary &&
            Object.keys(state.discoverySummary.summary).length > 0 && (
              <div
                className="rounded p-4"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  border: "1px solid var(--color-sentinel-border)",
                }}
              >
                <h4
                  className="text-sm font-semibold mb-2"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  Classification Summary
                </h4>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  {Object.entries(state.discoverySummary.summary).map(
                    ([key, val]) => (
                      <div
                        key={key}
                        className="flex justify-between"
                        style={{
                          color: "var(--color-sentinel-text-secondary)",
                        }}
                      >
                        <span className="capitalize">
                          {key.replace(/_/g, " ")}
                        </span>
                        <span
                          className="font-medium"
                          style={{
                            color: "var(--color-sentinel-text-primary)",
                          }}
                        >
                          {String(val)}
                        </span>
                      </div>
                    ),
                  )}
                </div>
              </div>
            )}
        </div>
      )}
    </div>
  );

  const renderStep3 = () => (
    <div className="space-y-5">
      <div>
        <h3
          className="text-lg font-semibold mb-1"
          style={{ color: "var(--color-sentinel-text-primary)" }}
        >
          Review Mappings
        </h3>
        <p
          className="text-sm"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          Review AI-classified equipment and point mappings. Low-confidence
          items are highlighted for manual review.
        </p>
      </div>

      {state.loading && (
        <div className="flex flex-col items-center gap-3 py-8">
          <Loader2
            className="w-10 h-10 animate-spin"
            style={{ color: "var(--color-sentinel-blue)" }}
          />
          <p
            className="text-sm"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            Loading mapping details...
          </p>
        </div>
      )}

      {state.error && (
        <div
          className="flex items-start gap-2 p-3 rounded text-sm"
          style={{
            background: "var(--color-sentinel-red)11",
            border: "1px solid var(--color-sentinel-red)",
            color: "var(--color-sentinel-red)",
          }}
        >
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <div>
            <p>{state.error}</p>
            <button
              onClick={handleLoadMappings}
              className="mt-2 underline text-xs"
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {state.mappings && !state.loading && (
        <div className="space-y-4">
          {/* Validation banner */}
          {state.mappings.needs_review > 0 && (
            <div
              className="flex items-center gap-2 p-3 rounded text-sm"
              style={{
                background: "var(--color-sentinel-amber)11",
                border: "1px solid var(--color-sentinel-amber)",
                color: "var(--color-sentinel-amber)",
              }}
            >
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>
                {state.mappings.needs_review} point
                {state.mappings.needs_review !== 1 ? "s" : ""} flagged for
                review (low confidence)
              </span>
            </div>
          )}

          {/* Confidence breakdown */}
          {state.mappings.confidence_breakdown && (
            <div className="flex gap-3">
              {Object.entries(state.mappings.confidence_breakdown).map(
                ([level, count]) => (
                  <div
                    key={level}
                    className="flex items-center gap-1.5 text-sm"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    <ConfidenceBadge confidence={level} />
                    <span>{count}</span>
                  </div>
                ),
              )}
            </div>
          )}

          {/* Equipment cards */}
          <div className="space-y-2">
            {state.mappings.equipment.map((eq) => {
              const isExpanded = state.expandedEquipment.has(eq.equipment_id);
              return (
                <div
                  key={eq.equipment_id}
                  className="rounded overflow-hidden"
                  style={{
                    border: "1px solid var(--color-sentinel-border)",
                  }}
                >
                  {/* Equipment header — clickable */}
                  <button
                    onClick={() =>
                      dispatch({
                        type: "TOGGLE_EQUIPMENT",
                        equipmentId: eq.equipment_id,
                      })
                    }
                    className="w-full flex items-center justify-between p-3 text-left transition-colors"
                    style={{
                      background: "var(--color-sentinel-bg-secondary)",
                    }}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      {isExpanded ? (
                        <ChevronDown
                          className="w-4 h-4 shrink-0"
                          style={{
                            color: "var(--color-sentinel-text-secondary)",
                          }}
                        />
                      ) : (
                        <ChevronRight
                          className="w-4 h-4 shrink-0"
                          style={{
                            color: "var(--color-sentinel-text-secondary)",
                          }}
                        />
                      )}
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span
                            className="text-sm font-semibold truncate"
                            style={{
                              color: "var(--color-sentinel-text-primary)",
                            }}
                          >
                            {eq.equipment_name}
                          </span>
                          <ConfidenceBadge confidence={eq.confidence} />
                        </div>
                        <span
                          className="text-xs"
                          style={{
                            color: "var(--color-sentinel-text-secondary)",
                          }}
                        >
                          {eq.equipment_type} · {eq.equipment_id} ·{" "}
                          {eq.points.length} points
                        </span>
                      </div>
                    </div>
                  </button>

                  {/* Expanded point list */}
                  {isExpanded && (
                    <div
                      className="border-t"
                      style={{
                        borderColor: "var(--color-sentinel-border)",
                        background: "var(--color-sentinel-bg-primary)",
                      }}
                    >
                      <table className="w-full text-sm">
                        <thead>
                          <tr
                            style={{
                              color: "var(--color-sentinel-text-secondary)",
                            }}
                          >
                            <th className="text-left px-3 py-2 font-medium">
                              Point Name
                            </th>
                            <th className="text-left px-3 py-2 font-medium">
                              Type
                            </th>
                            <th className="text-left px-3 py-2 font-medium">
                              Confidence
                            </th>
                            <th className="text-left px-3 py-2 font-medium">
                              Brick Class
                            </th>
                            <th className="text-left px-3 py-2 font-medium">
                              Unit
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {eq.points.map((pt, idx) => (
                            <tr
                              key={idx}
                              className="border-t"
                              style={{
                                borderColor: "var(--color-sentinel-border)",
                                color:
                                  pt.confidence === "low"
                                    ? "var(--color-sentinel-amber)"
                                    : "var(--color-sentinel-text-primary)",
                              }}
                            >
                              <td className="px-3 py-1.5 font-mono text-xs">
                                {pt.name}
                              </td>
                              <td className="px-3 py-1.5">{pt.point_type}</td>
                              <td className="px-3 py-1.5">
                                <ConfidenceBadge confidence={pt.confidence} />
                              </td>
                              <td className="px-3 py-1.5 text-xs">
                                {pt.brick_class || "\u2014"}
                              </td>
                              <td className="px-3 py-1.5 text-xs">
                                {pt.unit || "\u2014"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Totals */}
          <div
            className="text-sm"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            Total: {state.mappings.total_points} points across{" "}
            {state.mappings.equipment_count} equipment groups
          </div>
        </div>
      )}
    </div>
  );

  const renderStep4 = () => (
    <div className="space-y-5">
      <div>
        <h3
          className="text-lg font-semibold mb-1"
          style={{ color: "var(--color-sentinel-text-primary)" }}
        >
          Approve &amp; Activate
        </h3>
        <p
          className="text-sm"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          Confirm the classified mappings to create equipment models and
          activate monitoring.
        </p>
      </div>

      {state.approveStatus === "approved" ? (
        <div className="flex flex-col items-center gap-4 py-6">
          <CheckCircle
            className="w-16 h-16"
            style={{ color: "var(--color-sentinel-green)" }}
          />
          <h4
            className="text-xl font-semibold"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            Mappings Approved
          </h4>
          <p
            className="text-sm text-center"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            {state.approveResult?.equipment_created ?? 0} equipment model
            {(state.approveResult?.equipment_created ?? 0) !== 1 ? "s" : ""}{" "}
            created and monitoring activated.
          </p>
          {state.approveMessage && (
            <p
              className="text-xs text-center"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              {state.approveMessage}
            </p>
          )}
          <button
            onClick={() => {
              onComplete();
            }}
            className="px-6 py-2 rounded text-sm font-medium mt-2"
            style={{
              background: "var(--color-sentinel-green)",
              color: "#fff",
            }}
          >
            Done
          </button>
        </div>
      ) : (
        <>
          {/* Summary */}
          {state.mappings && (
            <div
              className="rounded p-4 space-y-3"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                border: "1px solid var(--color-sentinel-border)",
              }}
            >
              <h4
                className="text-sm font-semibold"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Activation Summary
              </h4>
              <div
                className="grid grid-cols-2 gap-2 text-sm"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                <span>Equipment to create:</span>
                <span
                  className="font-medium"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  {state.mappings.equipment_count}
                </span>
                <span>Total points:</span>
                <span
                  className="font-medium"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  {state.mappings.total_points}
                </span>
                <span>Needs review:</span>
                <span
                  className="font-medium"
                  style={{
                    color:
                      state.mappings.needs_review > 0
                        ? "var(--color-sentinel-amber)"
                        : "var(--color-sentinel-green)",
                  }}
                >
                  {state.mappings.needs_review}
                </span>
              </div>
            </div>
          )}

          {/* Approved by */}
          <div>
            <label
              className="block text-sm font-medium mb-1"
              style={labelStyle}
            >
              Approved By
            </label>
            <input
              type="text"
              value={state.approvedBy}
              onChange={(e) =>
                dispatch({
                  type: "SET_FIELD",
                  field: "approvedBy",
                  value: e.target.value,
                })
              }
              className="w-full max-w-xs rounded px-3 py-2 text-sm"
              style={inputStyle}
            />
          </div>

          {/* Error */}
          {state.approveStatus === "failed" && (
            <div
              className="flex items-start gap-2 p-3 rounded text-sm"
              style={{
                background: "var(--color-sentinel-red)11",
                border: "1px solid var(--color-sentinel-red)",
                color: "var(--color-sentinel-red)",
              }}
            >
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              <div>
                <p>{state.approveMessage}</p>
                <button
                  onClick={handleApprove}
                  className="mt-2 underline text-xs"
                >
                  Retry
                </button>
              </div>
            </div>
          )}

          {/* Approve button */}
          <button
            onClick={handleApprove}
            disabled={
              state.approveStatus === "approving" || !state.approvedBy
            }
            className="flex items-center gap-2 px-5 py-2 rounded text-sm font-medium transition-opacity disabled:opacity-50"
            style={{
              background: "var(--color-sentinel-green)",
              color: "#fff",
            }}
          >
            {state.approveStatus === "approving" ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <ShieldCheck className="w-4 h-4" />
            )}
            Approve &amp; Activate
          </button>
        </>
      )}
    </div>
  );

  // ============= Main Render =============

  const stepRenderers = [renderStep1, renderStep2, renderStep3, renderStep4];

  return (
    <div>
      <h2
        className="text-xl font-bold mb-6"
        style={{ color: "var(--color-sentinel-text-primary)" }}
      >
        BMS Connection Wizard
      </h2>

      <StepIndicator currentStep={state.step} />

      {/* Step content */}
      <div className="min-h-[300px]">{stepRenderers[state.step - 1]()}</div>

      {/* Navigation */}
      {state.step < 4 && (
        <div className="flex justify-between mt-8 pt-4 border-t" style={{ borderColor: "var(--color-sentinel-border)" }}>
          <button
            onClick={state.step === 1 ? onClose : goBack}
            className="px-4 py-2 rounded text-sm font-medium transition-opacity"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          >
            {state.step === 1 ? "Cancel" : "Back"}
          </button>
          <button
            onClick={goNext}
            disabled={!canGoNext()}
            className="px-4 py-2 rounded text-sm font-medium transition-opacity disabled:opacity-40"
            style={{
              background: "var(--color-sentinel-blue)",
              color: "#fff",
            }}
          >
            Next
          </button>
        </div>
      )}

      {/* Step 4 has its own Done/Approve buttons */}
      {state.step === 4 && state.approveStatus !== "approved" && (
        <div className="flex justify-start mt-8 pt-4 border-t" style={{ borderColor: "var(--color-sentinel-border)" }}>
          <button
            onClick={goBack}
            className="px-4 py-2 rounded text-sm font-medium"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          >
            Back
          </button>
        </div>
      )}
    </div>
  );
}

/** @deprecated Use BMSConnectionWizard */
export const NiagaraConnectionWizard = BMSConnectionWizard;

/** @deprecated Use BMSConnectionWizardProps */
export type NiagaraConnectionWizardProps = BMSConnectionWizardProps;

// ============= Helper sub-component =============

function SummaryCard({
  label,
  value,
  color,
}: {
  label: string;
  value: string | number;
  color: string;
}) {
  return (
    <div
      className="rounded p-3 text-center"
      style={{
        background: "var(--color-sentinel-bg-secondary)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
      <div className="text-2xl font-bold" style={{ color }}>
        {value}
      </div>
      <div
        className="text-xs mt-1"
        style={{ color: "var(--color-sentinel-text-secondary)" }}
      >
        {label}
      </div>
    </div>
  );
}
