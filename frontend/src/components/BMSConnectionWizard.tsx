import { useReducer, useCallback, useRef } from "react";
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
  MapPin,
  HelpCircle,
  Locate,
} from "lucide-react";
import type {
  Site,
  NiagaraMappingSummary,
  DiscoverClassifyResponse,
  BMSVendor,
  BACnetDevice,
  SimbiotCapabilitiesSummary,
} from '@/lib/api';
import { sitesApi } from '@/lib/api/sites';
import { siteGeocodeApi } from '@/lib/api/zone_ingestion';
import { siteProfileApi } from '@/lib/api/sites';
import { api, niagaraApi } from '@/lib/api';
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
  primaryObjective: string;  // cost | comfort | compliance | balanced
  // Geocoded location
  latitude: number | null;
  longitude: number | null;
  orientation_degrees: number | null;
  // BMS connection
  bmsVendor: BMSVendor;
  host: string;
  port: number;
  username: string;
  password: string;
  useHttps: boolean;
  siteId: string;  // Auto-generated on site creation
  discoveredDevices: BACnetDevice[];
  selectedDeviceId: number | null;
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
  capabilitySummary: SimbiotCapabilitiesSummary | null;
  capabilityError: string | null;
  loading: boolean;
  error: string | null;
  // Equipment verification
  showVerificationWizard: boolean;
  discoveryPhase: number; // 1-4: connect, scan, classify, group
  // Zone ingestion (optional, post-verification)
  showZoneIngestionWizard: boolean;
}

type WizardAction =
  | { type: "SET_FIELD"; field: string; value: string | number | boolean | null }
  | { type: "SET_BACNET_DEVICES"; devices: BACnetDevice[]; selectedDeviceId: number | null }
  | { type: "SET_CONNECTION_STATUS"; status: ConnectionStatus; message?: string }
  | { type: "SET_STEP"; step: number }
  | { type: "SET_DISCOVERY"; id: string; summary: DiscoverClassifyResponse }
  | { type: "SET_MAPPINGS"; mappings: NiagaraMappingSummary }
  | { type: "TOGGLE_EQUIPMENT"; equipmentId: string }
  | { type: "SET_APPROVE_STATUS"; status: ApproveStatus; message?: string; result?: { equipment_created: number } }
  | { type: "SET_CAPABILITIES"; summary: SimbiotCapabilitiesSummary | null; error?: string | null }
  | { type: "SET_LOADING"; loading: boolean }
  | { type: "SET_ERROR"; error: string | null }
  | { type: "SET_VERIFICATION_WIZARD"; show: boolean }
  | { type: "SET_DISCOVERY_PHASE"; phase: number }
  | { type: "SET_ZONE_INGESTION_WIZARD"; show: boolean }
  | { type: "SET_GEOCODE"; latitude: number | null; longitude: number | null; orientation_degrees: number | null; address?: string };

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
    case "SET_BACNET_DEVICES":
      return {
        ...state,
        discoveredDevices: action.devices,
        selectedDeviceId: action.selectedDeviceId,
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
    case "SET_CAPABILITIES":
      return {
        ...state,
        capabilitySummary: action.summary,
        capabilityError: action.error || null,
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
    case "SET_GEOCODE":
      return {
        ...state,
        latitude: action.latitude,
        longitude: action.longitude,
        orientation_degrees: action.orientation_degrees,
        siteAddress: action.address ?? state.siteAddress,
        loading: false,
      };
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
    primaryObjective: "balanced",
    // BMS connection
    bmsVendor: "niagara",
    host: "",
    port: 80,
    username: "",
    password: "",
    useHttps: false,
    siteId: initialSiteId || "",
    discoveredDevices: [],
    selectedDeviceId: null,
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
    capabilitySummary: null,
    capabilityError: null,
    loading: false,
    error: null,
    showVerificationWizard: false,
    discoveryPhase: 0,
    showZoneIngestionWizard: false,
  });
  const siteIdRef = useRef(initialSiteId || "");
  const createSitePromiseRef = useRef<Promise<string> | null>(null);

  const isNiagara = state.bmsVendor === "niagara";
  const vendorLabel = BMS_VENDORS.find((v) => v.value === state.bmsVendor)?.label ?? state.bmsVendor;

  const buildConnectionMessage = useCallback((devices: BACnetDevice[], selectedId: number | null): string => {
    const selected = devices.find((device) => device.device_id === selectedId) ?? null;
    if (selected) {
      return `Connected. Selected ${selected.object_name || `Device ${selected.device_id}`} at ${selected.ip_address}.`;
    }
    return `Connected. Found ${devices.length} BACnet device(s). Select the controller to continue.`;
  }, []);

  const pickDefaultDeviceId = useCallback((devices: BACnetDevice[], host: string): number | null => {
    if (devices.length === 0) return null;
    const normalizedHost = host.trim().toLowerCase();
    if (normalizedHost) {
      const exactMatch = devices.find((device) => device.ip_address.toLowerCase().startsWith(normalizedHost));
      if (exactMatch) return exactMatch.device_id;
    }
    return devices.length === 1 ? devices[0].device_id : null;
  }, []);

  const ensureSiteCreated = useCallback(async (): Promise<string> => {
    const existingSiteId = state.siteId || siteIdRef.current;
    if (existingSiteId) {
      siteIdRef.current = existingSiteId;
      return existingSiteId;
    }

    if (createSitePromiseRef.current) {
      return createSitePromiseRef.current;
    }

    createSitePromiseRef.current = sitesApi.create({
      name: state.siteName.trim(),
      address: state.siteAddress,
      region: state.siteRegion,
      type: state.siteType,
      floors: state.siteFloors
        .split(",")
        .map((floor) => floor.trim())
        .filter(Boolean),
      sqm: state.siteSqm,
    }).then(async (siteResult) => {
      siteIdRef.current = siteResult.id;
      dispatch({ type: "SET_FIELD", field: "siteId", value: siteResult.id });
      // Phase 191: create building profile after site exists
      // Building type mapping: wizard values → API values
      const BUILDING_TYPE_MAP: Record<string, string> = {
        office: "commercial_office",
        retail: "retail",
        hospital: "hospital",
        private_hospital: "hospital",
        industrial: "industrial",
        warehouse: "industrial",
        data_centre: "commercial_office",
        mixed_use: "mixed_use",
      };
      await siteProfileApi.create(siteResult.id, {
        building_type: BUILDING_TYPE_MAP[state.siteType] ?? state.siteType,
        primary_objective: state.primaryObjective,
        operating_schedule: {
          weekday_start: "08:00",
          weekday_end: "18:00",
          sunday_active: false,
          timezone: "Africa/Johannesburg",
          is_24_7: false,
        },
      });
      return siteResult.id;
    }).finally(() => {
      createSitePromiseRef.current = null;
    });

    return createSitePromiseRef.current;
  }, [state.siteAddress, state.siteFloors, state.siteId, state.siteName, state.siteRegion, state.siteSqm, state.siteType, state.primaryObjective]);

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

    if (!state.host.trim()) {
      dispatch({
        type: "SET_CONNECTION_STATUS",
        status: "failed",
        message: "Please enter the BMS host or IP address",
      });
      return;
    }

    try {
      if (state.bmsVendor === 'niagara') {
        const res = await niagaraApi.configureOBIX({
          host: state.host,
          port: state.port,
          username: state.username,
          password: state.password,
          use_https: state.useHttps,
          timeout: 10,
        });
        if (!res.connected) {
          dispatch({
            type: "SET_CONNECTION_STATUS",
            status: "failed",
            message: res.message,
          });
          return;
        }
      }

      const res = await niagaraApi.testBACnetConnection({
        timeout: 5,
        host: state.host.trim(),
      });

      if (res.count === 0) {
        dispatch({ type: "SET_BACNET_DEVICES", devices: [], selectedDeviceId: null });
        dispatch({
          type: "SET_CONNECTION_STATUS",
          status: "failed",
          message:
            "No BACnet devices matched this host. Check the controller IP, BACnet routing, and UDP port 47808.",
        });
        return;
      }

      const resolvedSiteId = await ensureSiteCreated();
      const selectedDeviceId = pickDefaultDeviceId(res.devices, state.host);
      dispatch({ type: "SET_BACNET_DEVICES", devices: res.devices, selectedDeviceId });
      dispatch({
        type: "SET_CONNECTION_STATUS",
        status: "connected",
        message: buildConnectionMessage(res.devices, selectedDeviceId),
      });
      try {
        const capabilities = await niagaraApi.getSimbiotCapabilities({
          site_id: resolvedSiteId,
          bms_vendor: state.bmsVendor,
          host: state.host.trim(),
          port: state.port,
          commissioning: true,
        });
        dispatch({ type: "SET_CAPABILITIES", summary: capabilities.summary, error: null });
      } catch (capErr) {
        dispatch({
          type: "SET_CAPABILITIES",
          summary: null,
          error: capErr instanceof Error ? capErr.message : "Could not load capabilities",
        });
      }
    } catch (err) {
      dispatch({
        type: "SET_CONNECTION_STATUS",
        status: "failed",
        message: err instanceof Error ? err.message : "Connection failed",
      });
    }
  }, [buildConnectionMessage, ensureSiteCreated, pickDefaultDeviceId, state.bmsVendor, state.host, state.password, state.port, state.siteName, state.useHttps, state.username]);

  // ---------- Step 2: Discover & Classify ----------
  const handleDiscover = useCallback(async () => {
    if (!state.siteId) {
      dispatch({ type: "SET_ERROR", error: "Create the site before starting discovery" });
      return;
    }
    if (state.selectedDeviceId == null) {
      dispatch({ type: "SET_ERROR", error: "Select the BACnet device to ingest before discovery" });
      return;
    }
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
        device_ip: state.host,
        site_id: state.siteId,
        device_bacnet_id: state.selectedDeviceId ?? undefined,
        adapter_type: "bacnet",
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
  }, [state.bmsVendor, state.host, state.selectedDeviceId, state.siteId]);

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
      if (res.success && state.siteId) {
        await api.toggleSiteProcessing(state.siteId, true);
      }
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
  }, [state.approvedBy, state.discoveryId, state.siteId]);

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
        return state.connectionStatus === "connected" && !!state.siteId && state.selectedDeviceId !== null;
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
          Enter details for your new building, then configure the BMS connection.
        </p>
      </div>

      {/* Help section */}
      <HelpSection title="Getting Started" variant="info">
        Enter your building details and connect to your BMS to automatically discover equipment.
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
          <MapPin className="w-5 h-5" style={{ color: "var(--color-sentinel-blue)" }} />
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

          {/* Address + Geocode */}
          <div className="col-span-2">
            <label className="block text-sm font-medium mb-1" style={labelStyle}>
              Address
            </label>
            <div className="flex gap-2">
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
                className="flex-1 rounded px-3 py-2 text-sm"
                style={inputStyle}
              />
              <button
                type="button"
                onClick={() => {
                  if (!state.siteAddress.trim()) return;
                  dispatch({ type: "SET_LOADING", loading: true });
                  siteGeocodeApi
                    .geocode(state.siteAddress)
                    .then((result) => {
                      dispatch({
                        type: "SET_GEOCODE",
                        latitude: result.lat,
                        longitude: result.lon,
                        orientation_degrees: result.orientation_degrees,
                        address: result.display_name,
                      });
                    })
                    .catch(() => dispatch({ type: "SET_LOADING", loading: false }));
                }}
                disabled={state.loading || !state.siteAddress.trim()}
                title="Look up address on map"
                className="flex items-center gap-1 px-3 py-2 rounded text-sm transition-colors"
                style={{
                  background: "var(--color-sentinel-blue)",
                  color: "white",
                  opacity: state.loading || !state.siteAddress.trim() ? 0.5 : 1,
                }}
              >
                <Locate className="w-4 h-4" />
              </button>
            </div>
            {state.latitude != null && state.longitude != null && (
              <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                📍 {state.latitude.toFixed(5)}, {state.longitude.toFixed(5)}
                {state.orientation_degrees != null && ` • ↗ ${state.orientation_degrees}°`}
              </p>
            )}
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

          {/* Primary Objective */}
          <div className="col-span-2 sm:col-span-1">
            <label className="block text-sm font-medium mb-1" style={labelStyle}>
              Optimisation Goal
            </label>
            <select
              value={state.primaryObjective}
              onChange={(e) =>
                dispatch({
                  type: "SET_FIELD",
                  field: "primaryObjective",
                  value: e.target.value,
                })
              }
              className="w-full rounded px-3 py-2 text-sm"
              style={inputStyle}
            >
              <option value="balanced">Balanced (cost + comfort)</option>
              <option value="cost">Cost minimisation</option>
              <option value="comfort">Occupant comfort</option>
              <option value="compliance">Regulatory compliance</option>
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
              dispatch({ type: "SET_BACNET_DEVICES", devices: [], selectedDeviceId: null });
              dispatch({ type: "SET_CAPABILITIES", summary: null, error: null });
              dispatch({
                type: "SET_FIELD",
                field: "port",
                value: e.target.value === "niagara" ? 80 : 47808,
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
        </div>
        {/* BMS Connection fields */}
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
                    value: parseInt(e.target.value, 10) || (isNiagara ? 80 : 47808),
                  })
                }
                className="w-full rounded px-3 py-2 text-sm"
                style={inputStyle}
              />
            </div>
            {isNiagara && (
              <>
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
              </>
            )}
            {state.discoveredDevices.length > 0 && (
              <div className="col-span-2">
                <label className="block text-sm font-medium mb-1" style={labelStyle}>
                  Discovered BACnet Device
                </label>
                <select
                  value={state.selectedDeviceId ?? ""}
                  onChange={(e) => {
                    const nextValue = e.target.value ? parseInt(e.target.value, 10) : null;
                    dispatch({ type: "SET_FIELD", field: "selectedDeviceId", value: nextValue });
                    dispatch({
                      type: "SET_CONNECTION_STATUS",
                      status: "connected",
                      message: buildConnectionMessage(state.discoveredDevices, nextValue),
                    });
                  }}
                  className="w-full rounded px-3 py-2 text-sm"
                  style={inputStyle}
                >
                  <option value="">Select a BACnet device</option>
                  {state.discoveredDevices.map((device) => (
                    <option key={device.device_id} value={device.device_id}>
                      {(device.object_name || `Device ${device.device_id}`)} · {device.ip_address} · ID {device.device_id}
                    </option>
                  ))}
                </select>
                <p className="text-xs mt-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Discovery and point ingestion will use this device instance. Control remains gated by site phase and modules.
                </p>
              </div>
            )}
          </div>
        {/* BACnet-only info for non-Niagara vendors */}
        {!isNiagara && (
          <div
            className="p-3 rounded text-sm mt-4"
            style={{
              background: "var(--color-sentinel-bg-primary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-secondary)",
            }}
          >
            No credentials are required for {vendorLabel}. SENTINEL will verify BACnet connectivity,
            list matching controllers for the host you entered, and use your selected device for discovery.
          </div>
        )}
      </div>

      {/* Test connection / Create Site button */}
      <button
        onClick={handleTestConnection}
        disabled={
          state.connectionStatus === "testing" ||
          !state.siteName.trim() ||
          !state.host.trim()
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
        Test Connection
      </button>

      {/* Connection result */}
      {state.connectionStatus === "connected" && (
        <div className="space-y-3">
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
          {state.capabilitySummary && (
            <div
              className="rounded p-3"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                border: "1px solid var(--color-sentinel-border)",
              }}
            >
              <p
                className="text-xs uppercase tracking-wide mb-2"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Control Capabilities (SIMBIOT)
              </p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                <SummaryCard label="Devices" value={state.capabilitySummary.devices} color="var(--color-sentinel-blue)" />
                <SummaryCard label="Points" value={state.capabilitySummary.points} color="var(--color-sentinel-text-primary)" />
                <SummaryCard label="Writable" value={state.capabilitySummary.writable_points} color="var(--color-sentinel-amber)" />
                <SummaryCard label="Controllable" value={state.capabilitySummary.controllable_devices} color="var(--color-sentinel-green)" />
              </div>
              {state.capabilitySummary.writable_points === 0 && (
                <p className="text-xs mt-2" style={{ color: "var(--color-sentinel-amber)" }}>
                  Telemetry-only mode detected. No writable command points exposed yet.
                </p>
              )}
            </div>
          )}
          {state.capabilityError && (
            <div
              className="text-xs px-3 py-2 rounded"
              style={{
                background: "var(--color-sentinel-red)11",
                border: "1px solid var(--color-sentinel-red)",
                color: "var(--color-sentinel-red)",
              }}
            >
              Capabilities check failed: {state.capabilityError}
            </div>
          )}
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
          Step 4: Approve &amp; Start Monitoring
        </h3>
        <p
          className="text-sm"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          Confirm the classified mappings to create equipment models and
          start data collection.
        </p>
      </div>

      {/* Help section */}
      <HelpSection title="Final Activation" variant="success">
        After approval, SENTINEL will create equipment models with v2.0 naming standard and
        auto-assigned zones. You'll then be offered to verify read-only telemetry before continuous
        data collection begins. Control and maintenance workflows remain disabled until their modules
        and policy gates are explicitly enabled.
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
            created and data collection activated.
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
        SIMBIOT Connection Wizard
      </h2>
      <p
        className="text-sm mb-8"
        style={{ color: "var(--color-sentinel-text-secondary)" }}
      >
        Connect your building management system to SENTINEL for AI-powered monitoring. Control stays gated until enabled.
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
