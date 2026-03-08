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
  Building2,
  MapPin,
  HelpCircle,
} from "lucide-react";
import type {
  Site,
  NiagaraMappingSummary,
  DiscoverClassifyResponse,
  BMSVendor,
} from '@/lib/api';
import { sitesApi } from '@/lib/api/sites';
import { niagaraApi } from '@/lib/api';
import { HelpSection } from "./HelpSection";
import { Tooltip } from "./Tooltip";
import { EquipmentVerificationWizard } from "./EquipmentVerificationWizard";
import { ZoneIngestionWizard } from "./wizards/ZoneIngestionWizard";

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

// ============= BMS Vendor Help Text =============

const VENDOR_HELP_TEXT: Record<BMSVendor, string> = {
  niagara: "Tridium Niagara uses oBIX for credential authentication and BACnet/IP for point discovery. Enter the JACE/Supervisor host IP and port (default 47808). The system will authenticate using provided credentials to access the object model.",
  desigo: "Siemens Desigo CC uses standard BACnet/IP without credential authentication. Ensure UDP port 47808 is open and accessible from this system. No username/password required—access is network-based.",
  metasys: "Johnson Controls Metasys uses BACnet/IP protocol. Configure the Metasys system to enable BACnet interoperability. Provide the gateway or controller IP address and ensure BACnet UDP 47808 is accessible.",
  honeywell: "Honeywell EBI (Enterprise Building Integrator) uses BACnet/IP for communications. Ensure the EBI gateway is accessible over the network. Verify BACnet services are enabled in your EBI configuration.",
  schneider: "Schneider EcoStruxure uses BACnet/IP for device discovery. Provide the IP address of your EcoStruxure gateway or controller. Ensure network connectivity and firewall rules allow BACnet communication.",
  trend: "Trend Controls IQ4 uses BACnet/IP for point access. Configure your IQ4 controller to accept BACnet queries. Enter the controller IP address and ensure UDP 47808 is accessible.",
  generic: "For generic BACnet/IP systems, provide the controller or gateway IP address. The system will discover points using standard BACnet protocol. Works with any BACnet/IP-compliant device.",
};

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
  // New site details
  siteName: string;
  siteAddress: string;
  siteRegion: string;
  siteType: string;
  siteFloors: string;  // Comma-separated list
  siteSqm: number;
  // BMS connection
  bmsVendor: BMSVendor;
  host: string;
  port: number;
  username: string;
  password: string;
  useHttps: boolean;
  useSimulation: boolean;  // Discover equipment from simulation database instead of live BMS
  siteId: string;  // Auto-generated on site creation
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
  // Equipment verification
  showVerificationWizard: boolean;
  discoveryPhase: number; // 1-4: connect, scan, classify, group
  // Zone ingestion (optional, post-verification)
  showZoneIngestionWizard: boolean;
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
  | { type: "SET_ERROR"; error: string | null }
  | { type: "SET_VERIFICATION_WIZARD"; show: boolean }
  | { type: "SET_DISCOVERY_PHASE"; phase: number }
  | { type: "SET_ZONE_INGESTION_WIZARD"; show: boolean };

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
    case "SET_VERIFICATION_WIZARD":
      return { ...state, showVerificationWizard: action.show };
    case "SET_DISCOVERY_PHASE":
      return { ...state, discoveryPhase: action.phase };
    case "SET_ZONE_INGESTION_WIZARD":
      return { ...state, showZoneIngestionWizard: action.show };
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
  sites: _sites,  // Kept for backward compatibility, not used in new onboarding flow
  onClose,
  onComplete,
}: BMSConnectionWizardProps) {
  const [state, dispatch] = useReducer(wizardReducer, {
    step: 1,
    // New site details
    siteName: "",
    siteAddress: "",
    siteRegion: "Gauteng",
    siteType: "office",
    siteFloors: "G, L1, L2",
    siteSqm: 5000,
    // BMS connection
    bmsVendor: "niagara",
    host: "",
    port: 80,
    username: "",
    password: "",
    useHttps: false,
    useSimulation: true,  // Default to simulation mode for wizard
    siteId: initialSiteId || "",
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
    showVerificationWizard: false,
    discoveryPhase: 0,
    showZoneIngestionWizard: false,
  });

  const isNiagara = state.bmsVendor === "niagara";
  const vendorLabel = BMS_VENDORS.find((v) => v.value === state.bmsVendor)?.label ?? state.bmsVendor;

  // ---------- Step 1: Test Connection ----------
  const handleTestConnection = useCallback(async () => {
    dispatch({ type: "SET_CONNECTION_STATUS", status: "testing" });
    dispatch({ type: "SET_ERROR", error: null });

    // Validate site name is provided
    if (!state.siteName.trim()) {
      dispatch({
        type: "SET_CONNECTION_STATUS",
        status: "failed",
        message: "Please enter a site name",
      });
      return;
    }

    if (state.useSimulation) {
      // Simulation mode: create the site, discovery will pull from Supabase
      try {
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-ignore - Type mismatch in CreateSiteRequest, but API accepts number
        const siteResult = await sitesApi.create({
          code: state.siteName.toLowerCase().replace(/\s+/g, '-'),
          name: state.siteName,
          address: state.siteAddress,
          type: state.siteType,
          // eslint-disable-next-line @typescript-eslint/ban-ts-comment
          // @ts-ignore - square_meters type mismatch
          square_meters: state.siteSqm ? parseInt(state.siteSqm, 10) : undefined,
        } as any);

        // Store the created site ID
        dispatch({ type: "SET_FIELD", field: "siteId", value: siteResult.id });

        dispatch({
          type: "SET_CONNECTION_STATUS",
          status: "connected",
          message: `Site "${state.siteName}" created (${siteResult.id}). Equipment will be discovered from the simulation database.`,
        });
      } catch (err) {
        dispatch({
          type: "SET_CONNECTION_STATUS",
          status: "failed",
          message: err instanceof Error ? err.message : "Failed to create site",
        });
      }
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
  }, [state.bmsVendor, state.host, state.port, state.username, state.password, state.useHttps, state.useSimulation, state.siteName, state.siteAddress, state.siteType, state.siteSqm]);

  // ---------- Step 2: Discover & Classify ----------
  const handleDiscover = useCallback(async () => {
    dispatch({ type: "SET_LOADING", loading: true });
    dispatch({ type: "SET_ERROR", error: null });
    dispatch({ type: "SET_DISCOVERY_PHASE", phase: 1 }); // Connecting...

    try {
      // Simulate discovery phases with delays
      await new Promise(r => setTimeout(r, 500));
      dispatch({ type: "SET_DISCOVERY_PHASE", phase: 2 }); // Scanning points...

      await new Promise(r => setTimeout(r, 800));
      dispatch({ type: "SET_DISCOVERY_PHASE", phase: 3 }); // Classifying equipment...

      const res = await niagaraApi.discoverAndClassify({
        device_ip: state.useSimulation ? "simulation" : state.host,
        site_id: state.siteId,
        bms_vendor: state.bmsVendor,
      });
      dispatch({ type: "SET_DISCOVERY_PHASE", phase: 4 }); // Grouping into zones...
      await new Promise(r => setTimeout(r, 300));

      dispatch({ type: "SET_DISCOVERY", id: res.discovery_id, summary: res });
      dispatch({ type: "SET_DISCOVERY_PHASE", phase: 0 });
    } catch (err) {
      dispatch({
        type: "SET_ERROR",
        error: err instanceof Error ? err.message : "Discovery failed",
      });
      dispatch({ type: "SET_DISCOVERY_PHASE", phase: 0 });
    }
  }, [state.host, state.siteId, state.useSimulation, state.bmsVendor]);

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

      // Launch verification wizard on success
      if (res.success) {
        // Give user a moment to see the success message
        setTimeout(() => {
          dispatch({ type: "SET_VERIFICATION_WIZARD", show: true });
        }, 1000);
      }
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

  // Site type options
  const SITE_TYPES = [
    { value: "office", label: "Office" },
    { value: "retail", label: "Retail" },
    { value: "hospital", label: "Hospital" },
    { value: "private_hospital", label: "Private Hospital" },
    { value: "industrial", label: "Industrial" },
    { value: "warehouse", label: "Warehouse" },
    { value: "data_centre", label: "Data Centre" },
    { value: "mixed_use", label: "Mixed Use" },
  ];

  const REGIONS = [
    "Gauteng",
    "Western Cape",
    "KwaZulu-Natal",
    "Eastern Cape",
    "Free State",
    "Limpopo",
    "Mpumalanga",
    "North West",
    "Northern Cape",
  ];

  // ============= Render Steps =============

  const renderStep1 = () => (
    <div className="space-y-5">
      <div>
        <h3
          className="text-lg font-semibold mb-1"
          style={{ color: "var(--color-sentinel-text-primary)" }}
        >
          Step 1: Ingest New Building
        </h3>
        <p
          className="text-sm"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          Enter details for your new building, then configure the BMS connection or select demo data.
        </p>
      </div>

      {/* Help section */}
      <HelpSection title="Getting Started" variant="info">
        Enter your building details and choose how to connect to your BMS. For testing and demos,
        select <strong>Demo Data</strong> to load pre-configured equipment. For production, enter
        your BMS connection details to automatically discover equipment.
      </HelpSection>

      {/* New Site Details Section */}
      <div
        className="rounded-lg p-4"
        style={{
          background: "var(--color-sentinel-bg-secondary)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="flex items-center gap-2 mb-3">
          <Building2 className="w-5 h-5" style={{ color: "var(--color-sentinel-blue)" }} />
          <h4
            className="text-sm font-semibold"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            New Site Details
          </h4>
        </div>

        <div className="grid grid-cols-2 gap-4">
          {/* Site Name */}
          <div className="col-span-2">
            <label className="block text-sm font-medium mb-1 flex items-center gap-2" style={labelStyle}>
              <span>Site Name *</span>
              <Tooltip content="Unique identifier for this building (e.g., 'Sandton City Tower', 'Client Hospital')">
                <HelpCircle className="w-4 h-4 text-gray-400 hover:text-blue-500 cursor-help" />
              </Tooltip>
            </label>
            <input
              type="text"
              value={state.siteName}
              onChange={(e) =>
                dispatch({
                  type: "SET_FIELD",
                  field: "siteName",
                  value: e.target.value,
                })
              }
              placeholder="e.g., Client Hospital, Main Office Tower"
              className="w-full rounded px-3 py-2 text-sm"
              style={inputStyle}
            />
          </div>

          {/* Address */}
          <div className="col-span-2">
            <label className="block text-sm font-medium mb-1" style={labelStyle}>
              Address
            </label>
            <input
              type="text"
              value={state.siteAddress}
              onChange={(e) =>
                dispatch({
                  type: "SET_FIELD",
                  field: "siteAddress",
                  value: e.target.value,
                })
              }
              placeholder="123 Main Street, City"
              className="w-full rounded px-3 py-2 text-sm"
              style={inputStyle}
            />
          </div>

          {/* Region */}
          <div className="col-span-2 sm:col-span-1">
            <label className="block text-sm font-medium mb-1" style={labelStyle}>
              Region
            </label>
            <select
              value={state.siteRegion}
              onChange={(e) =>
                dispatch({
                  type: "SET_FIELD",
                  field: "siteRegion",
                  value: e.target.value,
                })
              }
              className="w-full rounded px-3 py-2 text-sm"
              style={inputStyle}
            >
              {REGIONS.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>

          {/* Type */}
          <div className="col-span-2 sm:col-span-1">
            <label className="block text-sm font-medium mb-1" style={labelStyle}>
              Building Type
            </label>
            <select
              value={state.siteType}
              onChange={(e) =>
                dispatch({
                  type: "SET_FIELD",
                  field: "siteType",
                  value: e.target.value,
                })
              }
              className="w-full rounded px-3 py-2 text-sm"
              style={inputStyle}
            >
              {SITE_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          {/* Floors */}
          <div className="col-span-2 sm:col-span-1">
            <label className="block text-sm font-medium mb-1" style={labelStyle}>
              Floors (comma-separated)
            </label>
            <input
              type="text"
              value={state.siteFloors}
              onChange={(e) =>
                dispatch({
                  type: "SET_FIELD",
                  field: "siteFloors",
                  value: e.target.value,
                })
              }
              placeholder="B1, G, L1, L2, L3"
              className="w-full rounded px-3 py-2 text-sm"
              style={inputStyle}
            />
          </div>

          {/* sqm */}
          <div className="col-span-2 sm:col-span-1">
            <label className="block text-sm font-medium mb-1" style={labelStyle}>
              Floor Area (sqm)
            </label>
            <input
              type="number"
              value={state.siteSqm}
              onChange={(e) =>
                dispatch({
                  type: "SET_FIELD",
                  field: "siteSqm",
                  value: parseInt(e.target.value, 10) || 0,
                })
              }
              className="w-full rounded px-3 py-2 text-sm"
              style={inputStyle}
            />
          </div>
        </div>
      </div>

      {/* BMS Connection Section */}
      <div
        className="rounded-lg p-4"
        style={{
          background: "var(--color-sentinel-bg-secondary)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="flex items-center gap-2 mb-3">
          <Wifi className="w-5 h-5" style={{ color: "var(--color-sentinel-blue)" }} />
          <h4
            className="text-sm font-semibold"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            BMS Connection
          </h4>
        </div>

        {/* BMS Vendor selector */}
        <div className="mb-4">
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
          {/* Vendor-specific help text */}
          {state.bmsVendor && (
            <div
              className="mt-2 p-2 rounded text-xs"
              style={{
                background: "var(--color-sentinel-blue)11",
                color: "var(--color-sentinel-text-secondary)",
                border: "1px solid var(--color-sentinel-blue)22",
              }}
            >
              <p className="flex items-start gap-2">
                <HelpCircle className="w-3 h-3 mt-0.5 shrink-0" style={{ color: "var(--color-sentinel-blue)" }} />
                <span>{VENDOR_HELP_TEXT[state.bmsVendor]}</span>
              </p>
            </div>
          )}
        </div>\n\n        {/* Connection Mode Toggle */}
        <div className="space-y-2">
          {/* Connect to BMS option */}
          <label
            className="flex items-center gap-3 p-3 rounded cursor-pointer"
            style={{
              background: !state.useSimulation
                ? "var(--color-sentinel-blue)11"
                : "transparent",
              border: `1px solid ${!state.useSimulation ? "var(--color-sentinel-blue)" : "var(--color-sentinel-border)"}`,
            }}
          >
            <input
              type="radio"
              name="connectionMode"
              checked={!state.useSimulation}
              onChange={() =>
                dispatch({
                  type: "SET_FIELD",
                  field: "useSimulation",
                  value: false,
                })
              }
              className="w-4 h-4"
            />
            <div>
              <span
                className="text-sm font-medium"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Connect to BMS
              </span>
              <p
                className="text-xs mt-0.5"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Connect to a live BMS system via BACnet/oBIX
              </p>
            </div>
          </label>

          {/* Discover from Simulation option */}
          <label
            className="flex items-center gap-3 p-3 rounded cursor-pointer"
            style={{
              background: state.useSimulation
                ? "var(--color-sentinel-blue)11"
                : "transparent",
              border: `1px solid ${state.useSimulation ? "var(--color-sentinel-blue)" : "var(--color-sentinel-border)"}`,
            }}
          >
            <input
              type="radio"
              name="connectionMode"
              checked={state.useSimulation}
              onChange={() =>
                dispatch({
                  type: "SET_FIELD",
                  field: "useSimulation",
                  value: true,
                })
              }
              className="w-4 h-4"
            />
            <div>
              <span
                className="text-sm font-medium"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Discover from Simulation
              </span>
              <p
                className="text-xs mt-0.5"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Equipment will be discovered from the simulation database
              </p>
            </div>
          </label>
        </div>

        {/* BMS Connection fields — shown when Connect to BMS is selected */}
        {!state.useSimulation && isNiagara && (
          <div className="grid grid-cols-2 gap-4 mt-4">
            <div className="col-span-2 sm:col-span-1">
              <label className="block text-sm font-medium mb-1 flex items-center gap-2" style={labelStyle}>
                <span>Host / IP Address</span>
                <Tooltip content="IP address of your BMS controller, JACE, or Supervisor (e.g., 192.168.1.100)">
                  <HelpCircle className="w-4 h-4 text-gray-400 hover:text-blue-500 cursor-help" />
                </Tooltip>
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
              <label className="block text-sm font-medium mb-1 flex items-center gap-2" style={labelStyle}>
                <span>Port</span>
                <Tooltip content="BACnet/IP port (default 47808) or oBIX port (default 80, 443 for HTTPS)">
                  <HelpCircle className="w-4 h-4 text-gray-400 hover:text-blue-500 cursor-help" />
                </Tooltip>
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
              <label className="block text-sm font-medium mb-1 flex items-center gap-2" style={labelStyle}>
                <span>Username</span>
                <Tooltip content="oBIX credential (required for Niagara). Leave blank for BACnet-only systems.">
                  <HelpCircle className="w-4 h-4 text-gray-400 hover:text-blue-500 cursor-help" />
                </Tooltip>
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
              <label className="block text-sm font-medium mb-1 flex items-center gap-2" style={labelStyle}>
                <span>Password</span>
                <Tooltip content="oBIX credential (required for Niagara). Encrypted and never stored in logs.">
                  <HelpCircle className="w-4 h-4 text-gray-400 hover:text-blue-500 cursor-help" />
                </Tooltip>
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
                <span className="text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  Use HTTPS
                </span>
              </label>
            </div>
          </div>
        )}

        {/* BACnet-only info for non-Niagara vendors (not in simulation mode) */}
        {!state.useSimulation && !isNiagara && (
          <div
            className="p-3 rounded text-sm mt-4"
            style={{
              background: "var(--color-sentinel-bg-primary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-secondary)",
            }}
          >
            No credentials required. SENTINEL will broadcast a BACnet WhoIs on the local network (UDP port 47808) to discover {vendorLabel} controllers.
          </div>
        )}
      </div>

      {/* Test connection / Create Site button */}
      <button
        onClick={handleTestConnection}
        disabled={
          state.connectionStatus === "testing" ||
          !state.siteName.trim() ||
          (!state.useSimulation && isNiagara && !state.host)
        }
        className="flex items-center gap-2 px-4 py-2 rounded text-sm font-medium transition-opacity disabled:opacity-50"
        style={{
          background: "var(--color-sentinel-blue)",
          color: "#fff",
        }}
      >
        {state.connectionStatus === "testing" ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : state.useSimulation ? (
          <Building2 className="w-4 h-4" />
        ) : (
          <Wifi className="w-4 h-4" />
        )}
        {state.useSimulation ? "Create Site & Discover" : "Test Connection"}
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
          Step 2: Discover &amp; Classify Points
        </h3>
        <p
          className="text-sm"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          AI is scanning BACnet points and classifying them into equipment
          groups using Brick Schema ontology.
        </p>
      </div>

      {/* Help section */}
      <HelpSection title="What's Happening" variant="info">
        SENTINEL is discovering BACnet points from your BMS and using AI to classify them into
        equipment groups. This involves connecting to the BMS, scanning available points, and
        analyzing their names and characteristics to infer equipment types and zones.
      </HelpSection>

      {state.loading && (
        <div className="space-y-4 py-6">
          {/* Discovery progress indicator */}
          <ol className="space-y-3">
            {[
              { phase: 1, label: "Connecting to BMS" },
              { phase: 2, label: "Scanning BACnet points" },
              { phase: 3, label: "AI classifying equipment" },
              { phase: 4, label: "Grouping into zones" },
            ].map(({ phase, label }) => (
              <li
                key={phase}
                className={`flex items-center gap-3 text-sm transition-colors ${
                  state.discoveryPhase >= phase
                    ? "text-green-600 font-medium"
                    : "text-gray-500"
                }`}
              >
                <div
                  className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-semibold ${
                    state.discoveryPhase > phase
                      ? "bg-green-600 text-white"
                      : state.discoveryPhase === phase
                        ? "bg-blue-500 text-white"
                        : "bg-gray-300 text-white"
                  }`}
                >
                  {state.discoveryPhase > phase ? (
                    <CheckCircle className="w-3 h-3" />
                  ) : state.discoveryPhase === phase ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    phase
                  )}
                </div>
                <span>{label}</span>
              </li>
            ))}
          </ol>
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
                  className="text-sm font-semibold mb-3"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  Classification Summary
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {Object.entries(state.discoverySummary.summary).map(
                    ([key, val]) => {
                      // Skip arrays and complex objects in top-level display
                      if (Array.isArray(val)) return null;

                      // Handle nested objects (like equipment_type_counts, confidence_counts)
                      if (typeof val === "object" && val !== null) {
                        return (
                          <div
                            key={key}
                            className="rounded p-3"
                            style={{
                              background: "var(--color-sentinel-bg-primary)",
                              border: "1px solid var(--color-sentinel-border)",
                            }}
                          >
                            <h5
                              className="text-xs font-semibold mb-2 capitalize"
                              style={{ color: "var(--color-sentinel-text-secondary)" }}
                            >
                              {key.replace(/_/g, " ")}
                            </h5>
                            <div className="space-y-1">
                              {Object.entries(val as Record<string, unknown>).map(
                                ([subKey, subVal]) => (
                                  <div
                                    key={subKey}
                                    className="flex justify-between text-sm"
                                  >
                                    <span
                                      className="capitalize"
                                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                                    >
                                      {subKey.replace(/_/g, " ")}
                                    </span>
                                    <span
                                      className="font-medium"
                                      style={{ color: "var(--color-sentinel-text-primary)" }}
                                    >
                                      {String(subVal)}
                                    </span>
                                  </div>
                                ),
                              )}
                            </div>
                          </div>
                        );
                      }

                      // Simple values (numbers, strings)
                      return (
                        <div
                          key={key}
                          className="flex justify-between text-sm"
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
                      );
                    },
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
          Step 3: Review Mappings
        </h3>
        <p
          className="text-sm"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          Review AI-classified equipment and point mappings. Zone information
          is auto-inferred from equipment locations.
        </p>
      </div>

      {/* Help section */}
      <HelpSection title="Reviewing Equipment" variant="info">
        Each equipment card shows the AI-classified type, confidence level, and auto-inferred zone
        information. Expand any card to see individual BACnet points. Equipment with low confidence
        (⚠️) should be reviewed carefully. All equipment IDs have been auto-converted to SENTINEL
        v2.0 standard format.
      </HelpSection>

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
            <div className="flex flex-wrap gap-3">
              {Object.entries(state.mappings.confidence_breakdown).map(
                ([level, count]) => (
                  <div
                    key={level}
                    className="flex items-center gap-2 px-3 py-1.5 rounded"
                    style={{
                      background: "var(--color-sentinel-bg-secondary)",
                      border: "1px solid var(--color-sentinel-border)",
                    }}
                  >
                    <ConfidenceBadge confidence={level} />
                    <span
                      className="text-sm font-medium"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      {count}
                    </span>
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
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span
                            className="text-sm font-semibold"
                            style={{
                              color: "var(--color-sentinel-text-primary)",
                            }}
                          >
                            {eq.equipment_name || eq.equipment_id || "Unknown Equipment"}
                          </span>
                          <ConfidenceBadge confidence={eq.confidence || "unknown"} />
                          {/* Zone badge from metadata if available */}
                          {(eq as any).metadata?.zone && (
                            <span
                              className="text-xs px-2 py-0.5 rounded"
                              style={{
                                background: "var(--color-sentinel-blue)22",
                                color: "var(--color-sentinel-blue)",
                                border: "1px solid var(--color-sentinel-blue)44",
                              }}
                            >
                              <MapPin className="w-3 h-3 inline mr-1" />
                              Floor {(eq as any).metadata.zone.floor} · Zone {(eq as any).metadata.zone.zone_letter}
                            </span>
                          )}
                        </div>
                        <span
                          className="text-xs"
                          style={{
                            color: "var(--color-sentinel-text-secondary)",
                          }}
                        >
                          {eq.equipment_type || "unknown"} · {eq.equipment_id} ·{" "}
                          {eq.points?.length || 0} points
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
                          {eq.points.map((pt: Record<string, unknown>, idx: number) => (
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
                                {(pt.name || pt.original_name || "—") as string}
                              </td>
                              <td className="px-3 py-1.5">{String(pt.point_type || "—")}</td>
                              <td className="px-3 py-1.5">
                                <ConfidenceBadge confidence={pt.confidence as string} />
                              </td>
                              <td className="px-3 py-1.5 text-xs">
                                {String(pt.brick_class || "—")}
                              </td>
                              <td className="px-3 py-1.5 text-xs">
                                {String(pt.unit || "—")}
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
          Step 4: Approve &amp; Activate
        </h3>
        <p
          className="text-sm"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          Confirm the classified mappings to create equipment models and
          activate monitoring.
        </p>
      </div>

      {/* Help section */}
      <HelpSection title="Final Activation" variant="success">
        After approval, SENTINEL will create equipment models with v2.0 naming standard and
        auto-assigned zones. You'll then be offered to verify equipment functionality before going
        fully live. All discovered equipment will be available for control and monitoring.
      </HelpSection>

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

          {/* Pre-Approval Checklist */}
          {state.mappings && (
            <div
              className="rounded p-4 space-y-3"
              style={{
                background: "var(--color-sentinel-green)11",
                border: "1px solid var(--color-sentinel-green)44",
              }}
            >
              <h4
                className="text-sm font-semibold flex items-center gap-2"
                style={{ color: "var(--color-sentinel-green)" }}
              >
                <ClipboardCheck className="w-4 h-4" />
                Pre-Approval Checklist
              </h4>
              <div className="space-y-2 text-sm">
                <div className="flex items-center gap-2">
                  <span style={{ color: "var(--color-sentinel-green)" }}>✓</span>
                  <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                    All equipment types correctly identified
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span style={{ color: "var(--color-sentinel-green)" }}>✓</span>
                  <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                    Equipment IDs converted to v2.0 standard (S###-TYPE-FLOOR-ZONE)
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span style={{ color: "var(--color-sentinel-green)" }}>✓</span>
                  <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                    Zones auto-assigned from equipment locations
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    style={{
                      color:
                        state.mappings.needs_review === 0
                          ? "var(--color-sentinel-green)"
                          : "var(--color-sentinel-amber)",
                    }}
                  >
                    {state.mappings.needs_review === 0 ? "✓" : "⚠️"}
                  </span>
                  <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                    {state.mappings.needs_review === 0
                      ? "No low-confidence items flagged"
                      : `${state.mappings.needs_review} item${state.mappings.needs_review !== 1 ? "s" : ""} need manual review`}
                  </span>
                </div>
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

  // Extract equipment list for verification wizard
  const discoveredEquipment = state.mappings?.equipment.map((eq) => ({
    id: eq.equipment_id,
    name: eq.equipment_name || eq.equipment_id,
    equipment_type: eq.equipment_type,
    zone: (eq as any).metadata?.zone
      ? `Floor ${(eq as any).metadata.zone.floor} · Zone ${(eq as any).metadata.zone.zone_letter}`
      : undefined,
    point_count: eq.points?.length || 0,
  })) || [];

  return (
    <div className="max-w-5xl mx-auto">
      {/* Verification Wizard Modal */}
      {state.showVerificationWizard && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
          onClick={() => dispatch({ type: "SET_VERIFICATION_WIZARD", show: false })}
        >
          <div
            className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-6">
              <EquipmentVerificationWizard
                equipmentList={discoveredEquipment}
                onComplete={() => {
                  dispatch({ type: "SET_VERIFICATION_WIZARD", show: false });
                  // Offer zone configuration after equipment verification
                  setTimeout(() => {
                    dispatch({ type: "SET_ZONE_INGESTION_WIZARD", show: true });
                  }, 800);
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Zone Ingestion Wizard Modal */}
      {state.showZoneIngestionWizard && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
          onClick={() => dispatch({ type: "SET_ZONE_INGESTION_WIZARD", show: false })}
        >
          <div
            className="bg-white rounded-lg shadow-xl max-w-3xl w-full max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-6">
              <ZoneIngestionWizard
                siteId={state.siteId}
                onComplete={() => {
                  dispatch({ type: "SET_ZONE_INGESTION_WIZARD", show: false });
                  // Mark zone configuration as complete and trigger parent callback
                  onComplete?.();
                }}
                onSkip={() => {
                  // User chose to skip zone configuration for now
                  dispatch({ type: "SET_ZONE_INGESTION_WIZARD", show: false });
                  // Still trigger parent completion
                  onComplete?.();
                }}
                onCancel={() => {
                  dispatch({ type: "SET_ZONE_INGESTION_WIZARD", show: false });
                }}
              />
            </div>
          </div>
        </div>
      )}

      <h2
        className="text-2xl font-bold mb-2"
        style={{ color: "var(--color-sentinel-text-primary)" }}
      >
        BMS Connection Wizard
      </h2>
      <p
        className="text-sm mb-8"
        style={{ color: "var(--color-sentinel-text-secondary)" }}
      >
        Connect your building management system to SENTINEL for AI-powered monitoring and control.
      </p>

      <StepIndicator currentStep={state.step} />

      {/* Step content */}
      <div
        className="min-h-[400px] rounded-lg p-6"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        {stepRenderers[state.step - 1]()}
      </div>

      {/* Navigation */}
      {state.step < 4 && (
        <div className="flex justify-between mt-6">
          <button
            onClick={state.step === 1 ? onClose : goBack}
            className="px-5 py-2.5 rounded text-sm font-medium transition-opacity"
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
            className="px-5 py-2.5 rounded text-sm font-medium transition-opacity disabled:opacity-40"
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
        <div className="flex justify-start mt-6">
          <button
            onClick={goBack}
            className="px-5 py-2.5 rounded text-sm font-medium"
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
