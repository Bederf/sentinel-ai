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
  KeyRound,
  MapPin,
  HelpCircle,
  Locate,
  Settings,
  Upload,
} from "lucide-react";
import type {
  Site,
  BMSMappingSummary,
  DiscoverClassifyResponse,
  BMSVendor,
  BACnetDevice,
  SimbiotCapabilitiesSummary,
  SimbiotCapabilitiesResponse,
  NiagaraApproveResponse,
  OnboardingCanonicalizationSummary,
  OnboardingHierarchySummary,
} from '@/lib/api';
import { sitesApi, type OnboardingFactSource } from '@/lib/api/sites';
import { siteGeocodeApi } from '@/lib/api/zone_ingestion';
import { siteProfileApi } from '@/lib/api/sites';
import { api, bmsConnectionApi, resolveSimbiotProtocol, buildingConfigApi } from '@/lib/api';
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
  { value: "bridge" as const, label: "SIMBIOT Bridge (HTTP)", protocol: "Bridge API" },
  { value: "mqtt-bridge" as const, label: "MQTT (Shared Bridge)", protocol: "MQTT" },
  { value: "mqtt-direct" as const, label: "MQTT (Direct Broker)", protocol: "MQTT" },
];

// ============= BMS Vendor Help Text =============

const VENDOR_HELP_TEXT: Record<BMSVendor, string> = {
  niagara: "Tridium Niagara uses oBIX for credential authentication and BACnet/IP for point discovery. Enter the JACE/Supervisor host IP and port. The system will authenticate using provided credentials to access the object model.",
  desigo: "Siemens Desigo CC uses standard BACnet/IP without credential authentication. Ensure UDP port 47808 is open and accessible from this system. No username/password required—access is network-based.",
  metasys: "Johnson Controls Metasys uses BACnet/IP protocol. Configure the Metasys system to enable BACnet interoperability. Provide the gateway or controller IP address and ensure BACnet UDP 47808 is accessible.",
  honeywell: "Honeywell EBI (Enterprise Building Integrator) uses BACnet/IP for communications. Ensure the EBI gateway is accessible over the network. Verify BACnet services are enabled in your EBI configuration.",
  schneider: "Schneider EcoStruxure uses BACnet/IP for device discovery. Provide the IP address of your EcoStruxure gateway or controller. Ensure network connectivity and firewall rules allow BACnet communication.",
  trend: "Trend Controls IQ4 uses BACnet/IP for point access. Configure your IQ4 controller to accept BACnet queries. Enter the controller IP address and ensure UDP 47808 is accessible.",
  generic: "For generic BACnet/IP systems, provide the controller or gateway IP address. The system will discover points using standard BACnet protocol. Enter credentials if your BMS or gateway requires authentication.",
  bridge: "SIMBIOT Bridge uses HTTP REST to connect through the WireGuard bridge (port 8080). Enter the bridge IP and API token. No BACnet/UDP required — works through any tunnel.",
  "mqtt-bridge": "MQTT (Shared Bridge) connects via the shared Mosquitto instance (144.91.122.235:1883). Credentials and ACL are auto-provisioned per site. No manual broker config required.",
  "mqtt-direct": "MQTT (Direct Broker) connects to a broker you control. Enter the broker host/port and credentials. No auto-provisioning — you manage broker access.",
};

// ============= Types =============

export interface BMSConnectionWizardProps {
  siteId: string;
  requestedSiteId?: string;
  sites: Site[];
  onClose: () => void;
  onComplete: (siteId?: string) => void;
}

type ConnectionStatus = "idle" | "testing" | "connected" | "failed";
type ApproveStatus = "idle" | "approving" | "approved" | "failed";

interface WizardState {
  step: number;
  // New site details
  requestedSiteId: string;
  siteName: string;
  siteAddress: string;
  siteRegion: string;
  siteType: string;
  siteFloors: string;  // Comma-separated list
  siteSqm: number;
  yearBuilt: number;
  occupancyCapacity: number;
  totalDesks: number;
  parkingBays: number;
  nmdLimitKva: number;
  demandChargePerKva: number;
  electricityProvider: string;
  siteOperates24_7: boolean;
  weekdayStart: string;
  weekdayEnd: string;
  saturdayActive: boolean;
  sundayActive: boolean;
  clinicalZonesPresent: boolean;
  primaryObjective: string;  // cost | comfort | compliance | balanced
  // Geocoded location
  latitude: number | null;
  longitude: number | null;
  orientation_degrees: number | null;
  // Site contacts (Step 6)
  facilityManager: string;
  contactEmail: string;
  contactPhone: string;
  whatsappPhone: string;
  technicianEmails: string;
  tenantName: string;
  tenantAccessMode: string;
  tenantAccessConfirmed: boolean;
  bridgeDataFlowEnabled: boolean;
  // Connection method: network discovery or CSV upload
  connectionMethod: "network" | "csv";
  csvFile: File | null;
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
  mappings: BMSMappingSummary | null;
  expandedEquipment: Set<string>;
  approvedBy: string;
  approveStatus: ApproveStatus;
  approveMessage: string;
  approveResult: {
    equipment_created: number;
    canonicalization_summary?: OnboardingCanonicalizationSummary;
    hierarchy_summary?: OnboardingHierarchySummary;
  } | null;
  capabilitySummary: SimbiotCapabilitiesSummary | null;
  capabilityDetails: SimbiotCapabilitiesResponse | null;
  capabilityError: string | null;
  savedSiteLoading: boolean;
  savedSiteMessage: string;
  onboardingFactsLoading: boolean;
  onboardingFactsMessage: string;
  onboardingFactSources: Record<string, OnboardingFactSource>;
  onboardingFactsMissing: string[];
  loading: boolean;
  error: string | null;
  // Equipment verification
  showVerificationWizard: boolean;
  discoveryPhase: number; // 1-4: connect, scan, classify, group
  // Zone ingestion (optional, post-verification)
  showZoneIngestionWizard: boolean;
}

type WizardFieldValue = string | number | boolean | null | Record<string, OnboardingFactSource> | string[];

type WizardAction =
  | { type: "SET_FIELD"; field: string; value: WizardFieldValue }
  | { type: "SET_BACNET_DEVICES"; devices: BACnetDevice[]; selectedDeviceId: number | null }
  | { type: "SET_CONNECTION_STATUS"; status: ConnectionStatus; message?: string }
  | { type: "SET_STEP"; step: number }
  | { type: "SET_DISCOVERY"; id: string; summary: DiscoverClassifyResponse }
  | { type: "SET_MAPPINGS"; mappings: BMSMappingSummary }
  | { type: "RESET_DISCOVERY_REVIEW" }
  | { type: "TOGGLE_EQUIPMENT"; equipmentId: string }
  | {
      type: "SET_APPROVE_STATUS";
      status: ApproveStatus;
      message?: string;
      result?: {
        equipment_created: number;
        canonicalization_summary?: OnboardingCanonicalizationSummary;
        hierarchy_summary?: OnboardingHierarchySummary;
      };
    }
  | { type: "SET_CAPABILITIES"; summary: SimbiotCapabilitiesSummary | null; details?: SimbiotCapabilitiesResponse | null; error?: string | null }
  | { type: "SET_LOADING"; loading: boolean }
  | { type: "SET_ERROR"; error: string | null }
  | { type: "SET_VERIFICATION_WIZARD"; show: boolean }
  | { type: "SET_DISCOVERY_PHASE"; phase: number }
  | { type: "SET_ZONE_INGESTION_WIZARD"; show: boolean }
  | { type: "SET_GEOCODE"; latitude: number | null; longitude: number | null; orientation_degrees: number | null; address?: string }
  | { type: "SET_CSV_UPLOAD_RESULT"; discoveryId: string; summary: DiscoverClassifyResponse };

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
    case "RESET_DISCOVERY_REVIEW":
      return {
        ...state,
        discoveryId: null,
        discoverySummary: null,
        mappings: null,
        expandedEquipment: new Set<string>(),
        error: null,
      };
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
        capabilityDetails: action.details ?? null,
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
    case "SET_CSV_UPLOAD_RESULT":
      return {
        ...state,
        discoveryId: action.discoveryId,
        discoverySummary: action.summary,
        connectionStatus: "connected",
        connectionMessage: `CSV parsed — ${action.summary.points_count} points, ${action.summary.equipment_count} equipment groups`,
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
    { num: 5, label: "Access", icon: KeyRound },
    { num: 6, label: "Configure", icon: Settings },
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

function siteDisplayCode(siteId: string): string {
  const value = siteId.trim();
  if (!value) return "S---";
  const lower = value.toLowerCase();
  if (lower.startsWith("site-") && lower.length >= 8) {
    return `S${lower.slice(-3)}`.toUpperCase();
  }
  return value.toUpperCase();
}

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

function isHospitalType(siteType: string): boolean {
  return ["hospital", "private_hospital"].includes(siteType);
}

function wizardBuildingType(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (normalized === "commercial_office") return "office";
  if (normalized === "hospital") return "private_hospital";
  return normalized;
}

function parseWizardNumber(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function buildOperatingHours(state: WizardState): Record<string, unknown> {
  const timezone = "Africa/Johannesburg";
  const enabledDays = state.siteOperates24_7
    ? ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    : ["monday", "tuesday", "wednesday", "thursday", "friday"];
  const schedule = Object.fromEntries(
    ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"].map((day) => {
      const weekendEnabled = day === "saturday" ? state.saturdayActive : day === "sunday" ? state.sundayActive : true;
      const enabled = state.siteOperates24_7 || (enabledDays.includes(day) && weekendEnabled);
      return [
        day,
        {
          enabled,
          open: state.siteOperates24_7 ? "00:00" : state.weekdayStart,
          close: state.siteOperates24_7 ? "23:59" : state.weekdayEnd,
        },
      ];
    })
  );

  return {
    timezone,
    is_24_7: state.siteOperates24_7,
    weekday_start: state.siteOperates24_7 ? "00:00" : state.weekdayStart,
    weekday_end: state.siteOperates24_7 ? "23:59" : state.weekdayEnd,
    saturday_active: state.siteOperates24_7 || state.saturdayActive,
    sunday_active: state.siteOperates24_7 || state.sundayActive,
    ...schedule,
  };
}

function shouldPrefillString(current: string): boolean {
  return current.trim().length === 0;
}

function shouldPrefillNumber(current: number): boolean {
  return !Number.isFinite(current) || current <= 0;
}

function normalizeRequestedSiteId(value: string): string {
  return value.trim().toLowerCase();
}

function isValidRequestedSiteId(value: string): boolean {
  return value === "" || /^site-\d{3}$/.test(value);
}

function capabilityRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function capabilityString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function capabilityNumber(value: unknown): number {
  const parsed = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(parsed) ? parsed : 0;
}

function capabilityBoolean(value: unknown): boolean {
  return typeof value === "boolean" ? value : false;
}

function parseAdapterBaseUrl(baseUrl: string): { host: string; port: number; useHttps: boolean } {
  try {
    const url = new URL(baseUrl);
    return {
      host: url.hostname,
      port: Number(url.port) || (url.protocol === "https:" ? 443 : 80),
      useHttps: url.protocol === "https:",
    };
  } catch {
    const withoutProtocol = baseUrl.replace(/^https?:\/\//, "");
    const [host, port] = withoutProtocol.split(":");
    return { host: host || "", port: Number(port) || 8080, useHttps: baseUrl.startsWith("https://") };
  }
}

function deriveCapabilityEquipmentId(pointId: string, pointName: string, deviceId: string, index: number): string {
  const text = `${pointId} ${pointName}`.toUpperCase();
  const match = text.match(/\b(?:AHU|FCU|VAV|BOILER|BLR|CT|GEN|UPS|MEDGAS|BESS|PV|INV|FIRE|LIFT|CHILLER|CHWP|CWP|HWP|PUMP|METER|PM)[A-Z0-9_-]*(?:[-_ ][A-Z0-9]+){0,4}\b/);
  if (match?.[0]) {
    return match[0].replace(/\s+/g, "-");
  }

  const prefix = pointId.split(/[.:/]/)[0]?.trim();
  if (prefix && !["analog-input", "analog-output", "binary-input", "binary-output", "multi-state-input", "multi-state-output"].includes(prefix.toLowerCase())) {
    return prefix;
  }

  return deviceId ? `${deviceId}-unclassified` : `unclassified-${index + 1}`;
}

function inferCapabilityEquipmentType(equipmentId: string): string {
  const value = equipmentId.toLowerCase();
  if (value.includes("ccure") || value.includes("access") || value.includes("reader") || value.includes("badge")) return "access_control";
  if (value.includes("-door-") || value.includes("_door_")) return "access_control_door";
  if (value.includes("-gate-") || value.includes("_gate_") || value.includes("barrier")) return "access_control_gate";
  if (value.includes("cctv") || value.includes("camera")) return "cctv";
  if (value.includes("cold") || value.includes("freezer") || value.includes("fridge")) return "cold_room";
  if (value.includes("-zone-") || value.includes("_zone_")) return "zone_environment";
  if (value.includes("water-mtr") || value.includes("water_meter") || value.includes("water-meter")) return "water_meter";
  if (value.includes("-msb-") || value.includes("-mdb-") || value.includes("-db-")) return "electrical_distribution";
  if (value.includes("jace")) return "bms_controller";
  if (value.includes("-kef-") || value.includes("extract")) return "kitchen_extract_fan";
  if (value.includes("split")) return "split_ac";
  if (value.includes("medgas") || value.includes("medical-gas")) return "medical_gas";
  if (value.includes("ahu")) return "ahu";
  if (value.includes("fcu")) return "fcu";
  if (value.includes("vav")) return "vav";
  if (value.includes("boiler") || value.includes("blr")) return "boiler";
  if (value.includes("tower") || /\bct[-_]/.test(value)) return "cooling_tower";
  if (value.includes("gen")) return "generator";
  if (value.includes("ups")) return "ups";
  if (value.includes("bess")) return "battery_storage";
  if (value.includes("pv") || value.includes("inv")) return "solar";
  if (value.includes("fire")) return "fire_panel";
  if (value.includes("lift")) return "lift";
  if (value.includes("chiller")) return "chiller";
  if (value.includes("pump") || value.includes("chwp") || value.includes("cwp") || value.includes("hwp")) return "pump";
  if (value.includes("meter") || /\bpm[-_]/.test(value)) return "power_meter";
  return "unknown";
}

function inferCapabilityPointType(pointId: string, pointName: string, rawType: string): string {
  const value = `${pointId} ${pointName}`.toLowerCase();
  if (value.includes("temperature_sp") || value.includes("temp_sp") || value.includes("setpoint")) return "setpoint";
  if (value.includes("temperature") || value.includes(".temp") || value.includes("_temp")) return "temperature";
  if (value.includes("humidity")) return "humidity";
  if (value.includes("co2")) return "co2";
  if (value.includes("occupancy_pct")) return "occupancy_percent";
  if (value.includes("occupancy")) return "occupancy";
  if (value.includes("damper_position")) return "damper_position";
  if (value.includes("valve_position")) return "valve_position";
  if (value.includes("fan_speed")) return "fan_speed";
  if (value.includes("fan_status")) return "fan_status";
  if (value.includes("door_status")) return "door_status";
  if (value.includes("door_position")) return "door_position";
  if (value.includes("gate_position")) return "gate_position";
  if (value.includes("barrier_status")) return "barrier_status";
  if (value.includes("lock_status")) return "lock_status";
  if (value.includes("reader_status")) return "reader_status";
  if (value.includes("reader_format")) return "reader_format";
  if (value.includes("last_card_read")) return "last_card_read";
  if (value.includes("last_vehicle_read")) return "last_vehicle_read";
  if (value.includes("last_result")) return "access_result";
  if (value.includes("access_granted")) return "access_granted";
  if (value.includes("access_denied")) return "access_denied";
  if (value.includes("interlock_status")) return "interlock_status";
  if (value.includes("door_forced")) return "door_forced";
  if (value.includes("door_held")) return "door_held";
  if (value.includes("controller_status")) return "controller_status";
  if (value.includes("unlock_cmd")) return "unlock_command";
  if (value.includes("biometric_status")) return "biometric_status";
  if (value.includes("anpr_status")) return "anpr_status";
  if (value.includes("anpr_match")) return "anpr_match";
  if (value.includes("vehicle_count")) return "vehicle_count";
  if (value.includes("loop_status")) return "loop_status";
  if (value.includes("degradation")) return "degradation_status";
  if (value.includes("flow_rate")) return "flow_rate";
  if (value.includes("peak_flow")) return "peak_flow";
  if (value.includes("flow_direction")) return "flow_direction";
  if (value.includes("reverse_flow")) return "reverse_flow";
  if (value.includes("total_liters") || value.includes("total_m3")) return "totalized_consumption";
  if (value.includes("daily_liters") || value.includes("daily_demand")) return "daily_consumption";
  if (value.includes("hourly_liters")) return "hourly_consumption";
  if (value.includes("monthly_m3")) return "monthly_consumption";
  if (value.includes("leak_status")) return "leak_status";
  if (value.includes("sensor_fault")) return "sensor_fault";
  if (value.includes("meter_status")) return "meter_status";
  if (value.includes("low_pressure_alarm")) return "low_pressure_alarm";
  if (value.includes("high_pressure_alarm")) return "high_pressure_alarm";
  if (value.includes("mains_status")) return "mains_status";
  if (value.includes("power_factor")) return "power_factor";
  if (value.includes("total_kw")) return "power";
  if (value.includes("bacnet_device_count")) return "bacnet_device_count";
  if (value.includes("comms_status")) return "communications_status";
  if (value.includes("cpu_usage")) return "cpu_usage";
  if (value.includes("memory_usage")) return "memory_usage";
  if (value.includes("uptime_hours")) return "uptime";
  if (value.includes("fuel_level")) return "fuel_level";
  if (value.includes("load_percentage") || value.includes("load_pct")) return "load_percent";
  if (value.includes("pressure")) return "pressure";
  return rawType || "unknown";
}

function buildCapabilitiesMapping(details: SimbiotCapabilitiesResponse | null, siteId: string): BMSMappingSummary {
  const summary = details?.summary || { devices: 0, points: 0, writable_points: 0, controllable_devices: 0 };
  const groups = new Map<string, BMSMappingSummary["equipment"][number]>();
  let fallbackIndex = 0;

  for (const rawDevice of details?.devices || []) {
    const device = capabilityRecord(rawDevice);
    if (!device) continue;

    const deviceId = capabilityString(device.device_id) || `bridge-${siteId}`;
    const rawPoints = Array.isArray(device.points) ? device.points : [];
    rawPoints.forEach((rawPoint) => {
      const point = capabilityRecord(rawPoint);
      if (!point) return;

      const metadata = capabilityRecord(point.metadata) || {};
      const pointId = capabilityString(point.point_id);
      const pointName = capabilityString(point.point_name) || pointId;
      const equipmentId =
        capabilityString(metadata.equipment_id) ||
        deriveCapabilityEquipmentId(pointId, pointName, deviceId, fallbackIndex++);
      const equipmentType = inferCapabilityEquipmentType(equipmentId);
      const confidence = equipmentType === "unknown" ? "medium" : "high";

      if (!groups.has(equipmentId)) {
        groups.set(equipmentId, {
          equipment_id: equipmentId,
          equipment_name: equipmentId,
          equipment_type: equipmentType,
          confidence,
          points: [],
          point_count: 0,
        });
      }

      const group = groups.get(equipmentId);
      if (!group) return;

      group.points.push({
        name: pointId || pointName,
        original_name: pointName,
        point_type: inferCapabilityPointType(pointId, pointName, capabilityString(point.point_type)),
        confidence,
        brick_class: capabilityString(metadata.bacnet_object_type) || capabilityString(point.point_type) || undefined,
        unit: capabilityString(point.unit) || undefined,
      });
      group.point_count = group.points.length;
    });
  }

  if (groups.size === 0) {
    groups.set(`bridge-${siteId}`, {
      equipment_id: `bridge-${siteId}`,
      equipment_name: `Bridge Device (${siteId})`,
      equipment_type: "bridge",
      confidence: "medium",
      points: [],
      point_count: summary.points ?? 0,
    });
  }

  const equipment = Array.from(groups.values()).sort((a, b) => a.equipment_id.localeCompare(b.equipment_id));
  const confidenceBreakdown = equipment.reduce<Record<string, number>>((acc, item) => {
    acc[item.confidence] = (acc[item.confidence] || 0) + 1;
    return acc;
  }, {});

  return {
    discovery_id: `discovery-${siteId}`,
    status: "completed",
    equipment,
    validation: {},
    total_points: summary.points ?? equipment.reduce((sum, item) => sum + (item.point_count || item.points.length), 0),
    equipment_count: equipment.length,
    needs_review: equipment
      .filter((item) => item.equipment_type === "unknown")
      .reduce((sum, item) => sum + (item.point_count || item.points.length), 0),
    confidence_breakdown: confidenceBreakdown,
  };
}

// ============= Main Component =============

export function BMSConnectionWizard({
  siteId: initialSiteId,
  requestedSiteId: initialRequestedSiteId,
  sites,
  onClose,
  onComplete,
}: BMSConnectionWizardProps) {
  const [state, dispatch] = useReducer(wizardReducer, {
    step: 1,
    // New site details
    requestedSiteId: normalizeRequestedSiteId(initialRequestedSiteId || initialSiteId || ""),
    siteName: "",
    siteAddress: "",
    siteRegion: "Gauteng",
    siteType: "office",
    siteFloors: "G, L1, L2",
    siteSqm: 5000,
    yearBuilt: 0,
    occupancyCapacity: 0,
    totalDesks: 0,
    parkingBays: 0,
    nmdLimitKva: 0,
    demandChargePerKva: 0,
    electricityProvider: "",
    siteOperates24_7: false,
    weekdayStart: "08:00",
    weekdayEnd: "18:00",
    saturdayActive: false,
    sundayActive: false,
    clinicalZonesPresent: false,
    primaryObjective: "balanced",
    // Connection method
    connectionMethod: "network" as const,
    csvFile: null,
    // BMS connection
    bmsVendor: "niagara",
    host: "",
    port: "",
    username: "",
    password: "",
    useHttps: false,
    // Site contacts (Step 6)
    facilityManager: "",
    contactEmail: "",
    contactPhone: "",
    whatsappPhone: "",
    technicianEmails: "",
    tenantName: "",
    tenantAccessMode: "shadow_readonly",
    tenantAccessConfirmed: false,
    bridgeDataFlowEnabled: false,
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
    capabilityDetails: null,
    capabilityError: null,
    savedSiteLoading: false,
    savedSiteMessage: "",
    onboardingFactsLoading: false,
    onboardingFactsMessage: "",
    onboardingFactSources: {},
    onboardingFactsMissing: [],
    loading: false,
    error: null,
    showVerificationWizard: false,
    discoveryPhase: 0,
    showZoneIngestionWizard: false,
  });
  const siteIdRef = useRef(initialSiteId || "");
  const createSitePromiseRef = useRef<Promise<string> | null>(null);

  const usesObix = state.bmsVendor === "niagara";
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

  const handleLoadSavedSite = useCallback(async (siteCodeInput?: string) => {
    const siteCode = normalizeRequestedSiteId(siteCodeInput || state.requestedSiteId);
    if (!isValidRequestedSiteId(siteCode) || !siteCode) {
      dispatch({ type: "SET_FIELD", field: "savedSiteMessage", value: "Enter a site code like site-005 first." });
      return;
    }

    dispatch({ type: "SET_FIELD", field: "savedSiteLoading", value: true });
    dispatch({ type: "SET_FIELD", field: "savedSiteMessage", value: "" });
    dispatch({ type: "SET_ERROR", error: null });

    try {
      const [buildingResult, profileResult, adaptersResult] = await Promise.allSettled([
        sitesApi.getBuildingConfig(siteCode),
        siteProfileApi.get(siteCode),
        bmsConnectionApi.getSimbiotAdapterConfigs(siteCode),
      ]);

      if (buildingResult.status !== "fulfilled") {
        throw new Error("No saved site was found for that code.");
      }

      const building = buildingResult.value;
      const metadata = capabilityRecord(building.metadata) || {};
      const contacts = capabilityRecord(building.contacts) || {};
      const optimization = capabilityRecord(building.optimization) || {};
      const features = capabilityRecord(building.features) || {};

      siteIdRef.current = siteCode;
      dispatch({ type: "SET_FIELD", field: "requestedSiteId", value: siteCode });
      dispatch({ type: "SET_FIELD", field: "siteId", value: siteCode });
      dispatch({ type: "SET_FIELD", field: "siteName", value: building.name || building.display_name || "" });
      dispatch({ type: "SET_FIELD", field: "siteAddress", value: building.address || "" });
      dispatch({ type: "SET_FIELD", field: "siteRegion", value: building.region || state.siteRegion });
      dispatch({ type: "SET_FIELD", field: "siteType", value: wizardBuildingType(building.type || state.siteType) });
      if (Array.isArray(building.floors) && building.floors.length > 0) {
        dispatch({ type: "SET_FIELD", field: "siteFloors", value: building.floors.join(", ") });
      }
      dispatch({ type: "SET_FIELD", field: "siteSqm", value: capabilityNumber(building.sqm ?? metadata.sqm) });
      dispatch({ type: "SET_FIELD", field: "yearBuilt", value: capabilityNumber(metadata.year_built) });
      dispatch({ type: "SET_FIELD", field: "occupancyCapacity", value: capabilityNumber(metadata.occupancy_capacity) });
      dispatch({ type: "SET_FIELD", field: "totalDesks", value: capabilityNumber(metadata.total_desks) });
      dispatch({ type: "SET_FIELD", field: "parkingBays", value: capabilityNumber(metadata.parking_bays) });
      dispatch({ type: "SET_FIELD", field: "nmdLimitKva", value: capabilityNumber(metadata.nmd_limit_kva) });
      dispatch({ type: "SET_FIELD", field: "demandChargePerKva", value: capabilityNumber(metadata.demand_charge_per_kva) });
      dispatch({ type: "SET_FIELD", field: "electricityProvider", value: capabilityString(metadata.electricity_provider) });
      dispatch({ type: "SET_FIELD", field: "facilityManager", value: capabilityString(contacts.facility_manager) });
      dispatch({ type: "SET_FIELD", field: "contactEmail", value: capabilityString(contacts.email) });
      dispatch({ type: "SET_FIELD", field: "contactPhone", value: capabilityString(contacts.emergency) });
      dispatch({ type: "SET_FIELD", field: "whatsappPhone", value: capabilityString(contacts.whatsapp) });
      dispatch({
        type: "SET_GEOCODE",
        latitude: typeof building.latitude === "number" ? building.latitude : null,
        longitude: typeof building.longitude === "number" ? building.longitude : null,
        orientation_degrees: null,
      });
      dispatch({ type: "SET_FIELD", field: "primaryObjective", value: capabilityString(optimization.active_profile) || state.primaryObjective });
      dispatch({ type: "SET_FIELD", field: "clinicalZonesPresent", value: capabilityBoolean(features.clinical_zones) || isHospitalType(wizardBuildingType(building.type || "")) });

      if (profileResult.status === "fulfilled") {
        const profile = profileResult.value;
        dispatch({ type: "SET_FIELD", field: "siteType", value: wizardBuildingType(profile.building_type || building.type || state.siteType) });
        dispatch({
          type: "SET_FIELD",
          field: "primaryObjective",
          value: profile.primary_objective === "cost_saving" ? "cost" : profile.primary_objective || state.primaryObjective,
        });
        dispatch({ type: "SET_FIELD", field: "clinicalZonesPresent", value: !!profile.clinical_zones_present });
        const schedule = capabilityRecord(profile.operating_schedule);
        if (schedule) {
          dispatch({ type: "SET_FIELD", field: "siteOperates24_7", value: capabilityBoolean(schedule.is_24_7) });
          dispatch({ type: "SET_FIELD", field: "weekdayStart", value: capabilityString(schedule.weekday_start) || state.weekdayStart });
          dispatch({ type: "SET_FIELD", field: "weekdayEnd", value: capabilityString(schedule.weekday_end) || state.weekdayEnd });
          dispatch({ type: "SET_FIELD", field: "saturdayActive", value: capabilityBoolean(schedule.saturday_active) });
          dispatch({ type: "SET_FIELD", field: "sundayActive", value: capabilityBoolean(schedule.sunday_active) });
        }
      }

      if (adaptersResult.status === "fulfilled") {
        const adapter = adaptersResult.value.adapters.find((item) => item.enabled) || adaptersResult.value.adapters[0];
        if (adapter) {
          const protocolVendor: Record<string, BMSVendor> = {
            bridge: "bridge",
            obix: "niagara",
            bacnet: "generic",
            mqtt: "mqtt-bridge",
          };
          dispatch({ type: "SET_FIELD", field: "bmsVendor", value: protocolVendor[adapter.protocol] || "generic" });
          const config = capabilityRecord(adapter.connection_config) || {};
          const baseUrl = capabilityString(config.base_url);
          if (baseUrl) {
            const parsed = parseAdapterBaseUrl(baseUrl);
            dispatch({ type: "SET_FIELD", field: "host", value: parsed.host });
            dispatch({ type: "SET_FIELD", field: "port", value: parsed.port });
            dispatch({ type: "SET_FIELD", field: "useHttps", value: parsed.useHttps });
          } else {
            dispatch({ type: "SET_FIELD", field: "host", value: capabilityString(config.host) });
            dispatch({ type: "SET_FIELD", field: "port", value: capabilityNumber(config.port) || state.port });
            dispatch({ type: "SET_FIELD", field: "username", value: capabilityString(config.username) });
            dispatch({ type: "SET_FIELD", field: "useHttps", value: capabilityBoolean(config.use_https) || capabilityBoolean(config.use_tls) });
          }
        }
      }

      dispatch({ type: "SET_BACNET_DEVICES", devices: [], selectedDeviceId: null });
      dispatch({ type: "SET_CAPABILITIES", summary: null, details: null, error: null });
      dispatch({
        type: "SET_CONNECTION_STATUS",
        status: "idle",
        message: `Loaded saved details for ${siteCode}. Test the connection to refresh capabilities.`,
      });
      dispatch({ type: "SET_FIELD", field: "savedSiteMessage", value: `Loaded saved details for ${siteCode}.` });
    } catch (err) {
      dispatch({
        type: "SET_FIELD",
        field: "savedSiteMessage",
        value: err instanceof Error ? err.message : "Could not load saved site details.",
      });
    } finally {
      dispatch({ type: "SET_FIELD", field: "savedSiteLoading", value: false });
    }
  }, [state.primaryObjective, state.requestedSiteId, state.siteRegion, state.siteType, state.weekdayEnd, state.weekdayStart, state.port]);

  const handleScrapeOnboardingFacts = useCallback(async () => {
    dispatch({ type: "SET_FIELD", field: "onboardingFactsLoading", value: true });
    dispatch({ type: "SET_FIELD", field: "onboardingFactsMessage", value: "" });
    try {
      const result = await sitesApi.scrapeOnboardingFacts({
        site_name: state.siteName.trim(),
        address: state.siteAddress.trim(),
        building_type: state.siteType,
      });
      const values = result.values || {};

      if (values.address && shouldPrefillString(state.siteAddress)) {
        dispatch({ type: "SET_FIELD", field: "siteAddress", value: values.address });
      }
      if (typeof values.sqm === "number" && shouldPrefillNumber(state.siteSqm)) {
        dispatch({ type: "SET_FIELD", field: "siteSqm", value: values.sqm });
      }
      if (typeof values.year_built === "number" && shouldPrefillNumber(state.yearBuilt)) {
        dispatch({ type: "SET_FIELD", field: "yearBuilt", value: values.year_built });
      }
      if (typeof values.latitude === "number") {
        dispatch({ type: "SET_FIELD", field: "latitude", value: values.latitude });
      }
      if (typeof values.longitude === "number") {
        dispatch({ type: "SET_FIELD", field: "longitude", value: values.longitude });
      }
      if (values.contact_email && shouldPrefillString(state.contactEmail)) {
        dispatch({ type: "SET_FIELD", field: "contactEmail", value: values.contact_email });
      }
      if (values.contact_phone && shouldPrefillString(state.contactPhone)) {
        dispatch({ type: "SET_FIELD", field: "contactPhone", value: values.contact_phone });
      }
      if (values.whatsapp_phone && shouldPrefillString(state.whatsappPhone)) {
        dispatch({ type: "SET_FIELD", field: "whatsappPhone", value: values.whatsapp_phone });
      }
      if (values.electricity_provider && shouldPrefillString(state.electricityProvider)) {
        dispatch({ type: "SET_FIELD", field: "electricityProvider", value: values.electricity_provider });
      }
      if (typeof values.nmd_limit_kva === "number" && shouldPrefillNumber(state.nmdLimitKva)) {
        dispatch({ type: "SET_FIELD", field: "nmdLimitKva", value: values.nmd_limit_kva });
      }
      if (typeof values.demand_charge_per_kva === "number" && shouldPrefillNumber(state.demandChargePerKva)) {
        dispatch({ type: "SET_FIELD", field: "demandChargePerKva", value: values.demand_charge_per_kva });
      }

      dispatch({ type: "SET_FIELD", field: "onboardingFactSources", value: result.sources || {} });
      dispatch({ type: "SET_FIELD", field: "onboardingFactsMissing", value: result.missing || [] });
      const foundCount = Object.keys(result.sources || {}).length;
      const missingCount = result.missing?.length ?? 0;
      dispatch({
        type: "SET_FIELD",
        field: "onboardingFactsMessage",
        value: foundCount === 0
          ? "No public onboarding facts were extracted. Enter the remaining fields manually."
          : result.scrape_available
          ? `Prefilled ${foundCount} field${foundCount === 1 ? "" : "s"}. ${missingCount} still need manual confirmation.`
          : `Geocode/manual mode: Firecrawl did not return public facts. ${missingCount} fields still need manual completion.`,
      });
    } catch (error) {
      dispatch({
        type: "SET_FIELD",
        field: "onboardingFactsMessage",
        value: error instanceof Error ? error.message : "Could not scrape onboarding facts",
      });
    } finally {
      dispatch({ type: "SET_FIELD", field: "onboardingFactsLoading", value: false });
    }
  }, [
    state.contactEmail,
    state.contactPhone,
    state.demandChargePerKva,
    state.electricityProvider,
    state.nmdLimitKva,
    state.siteAddress,
    state.siteName,
    state.siteSqm,
    state.siteType,
    state.whatsappPhone,
    state.yearBuilt,
  ]);

  const ensureSiteCreated = useCallback(async (): Promise<string> => {
    const existingSiteId = state.siteId || siteIdRef.current;
    if (existingSiteId) {
      siteIdRef.current = existingSiteId;
      return existingSiteId;
    }

    if (createSitePromiseRef.current) {
      return createSitePromiseRef.current;
    }

    const operatingHours = buildOperatingHours(state);
    const profileBuildingType = BUILDING_TYPE_MAP[state.siteType] ?? state.siteType;
    const features = {
      hvac: true,
      dali: false,
      desk_diagnosis: state.totalDesks > 0,
      load_shedding_optimization: true,
    };
    const optimizationSettings = {
      mode: state.primaryObjective,
      active_profile: state.primaryObjective,
      sentinel_operating_mode:
        state.primaryObjective === "cost" ? "cost_saving" : state.primaryObjective === "comfort" ? "comfort" : "balanced",
      control_tier: "supervised",
    };
    const requestedSiteId = normalizeRequestedSiteId(state.requestedSiteId);

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
      year_built: state.yearBuilt || undefined,
      latitude: state.latitude ?? undefined,
      longitude: state.longitude ?? undefined,
      contact_phone: state.contactPhone || undefined,
      contact_email: state.contactEmail || undefined,
      whatsapp_phone: state.whatsappPhone || undefined,
      occupancy_capacity: state.occupancyCapacity || undefined,
      total_desks: state.totalDesks || undefined,
      parking_bays: state.parkingBays || undefined,
      nmd_limit_kva: state.nmdLimitKva || undefined,
      demand_charge_per_kva: state.demandChargePerKva || undefined,
      electricity_provider: state.electricityProvider || undefined,
      operating_hours: operatingHours,
      optimization_settings: optimizationSettings,
      features,
      ...(requestedSiteId && { id: requestedSiteId }),
    }).then(async (siteResult) => {
      siteIdRef.current = siteResult.id;
      dispatch({ type: "SET_FIELD", field: "siteId", value: siteResult.id });
      await siteProfileApi.create(siteResult.id, {
        building_type: profileBuildingType,
        primary_objective: state.primaryObjective,
        operating_schedule: operatingHours,
        tariff_structure: state.electricityProvider.toLowerCase().includes("eskom") ? "tou_megaflex" : "municipal",
        clinical_zones_present: state.clinicalZonesPresent || isHospitalType(state.siteType),
        regulatory_frameworks: isHospitalType(state.siteType)
          ? ["SANS_10400_XA", "SANS_10400_T", "LEGIONELLA"]
          : ["SANS_10400_XA"],
      });
      return siteResult.id;
    }).finally(() => {
      createSitePromiseRef.current = null;
    });

    return createSitePromiseRef.current;
  }, [state]);

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

    const portNum = Number(state.port);
    const portFallback = usesObix ? 80 : state.bmsVendor === 'bridge' ? 8080 : 47808;
    const safePort = state.port && Number.isFinite(portNum) && portNum > 0 && portNum <= 65535
      ? portNum
      : portFallback;
    const requestedSiteId = normalizeRequestedSiteId(state.requestedSiteId);
    if (!isValidRequestedSiteId(requestedSiteId)) {
      dispatch({
        type: "SET_CONNECTION_STATUS",
        status: "failed",
        message: "Site code must use the format site-005",
      });
      return;
    }
    if (requestedSiteId !== state.requestedSiteId) {
      dispatch({ type: "SET_FIELD", field: "requestedSiteId", value: requestedSiteId });
    }

    try {
      const isBridge = state.bmsVendor === 'bridge';
      const isMqttBridge = state.bmsVendor === 'mqtt-bridge';
      const isMqttDirect = state.bmsVendor === 'mqtt-direct';

      if (state.bmsVendor === 'niagara') {
        if (!state.host.trim()) {
          dispatch({
            type: "SET_CONNECTION_STATUS",
            status: "failed",
            message: "Please enter the BMS host or IP address",
          });
          return;
        }
        const res = await bmsConnectionApi.configureOBIX({
          host: state.host,
          port: safePort,
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

      if (isMqttDirect) {
        if (!state.host.trim()) {
          dispatch({
            type: "SET_CONNECTION_STATUS",
            status: "failed",
            message: "Please enter the MQTT broker host or IP address",
          });
          return;
        }
        if (safePort === portFallback && safePort === 47808) {
          dispatch({
            type: "SET_CONNECTION_STATUS",
            status: "failed",
            message: "Enter a valid MQTT broker port (typically 1883 or 8883 for TLS)",
          });
          return;
        }
        resolvedSiteId = await ensureSiteCreated();
        try {
          await bmsConnectionApi.saveSimbiotAdapterConfig({
            site_id: resolvedSiteId,
            protocol: "mqtt",
            config: {
              bms_vendor: "mqtt-direct",
              host: state.host.trim(),
              port: safePort,
              ...(state.username && { username: state.username }),
              ...(state.password && { password: state.password }),
            },
            enabled: true,
            poll_interval_seconds: 60,
          });
        } catch (saveErr) {
          console.warn("MQTT direct adapter config save failed", saveErr);
        }
        dispatch({ type: "SET_BACNET_DEVICES", devices: [], selectedDeviceId: null });
        dispatch({
          type: "SET_CONNECTION_STATUS",
          status: "connected",
          message: `MQTT broker configured — connecting to ${state.host.trim()}:${safePort}`,
        });
        return;
      }

      if (isMqttBridge) {
        resolvedSiteId = await ensureSiteCreated();
        try {
          await bmsConnectionApi.saveSimbiotAdapterConfig({
            site_id: resolvedSiteId,
            protocol: "mqtt",
            config: { bms_vendor: "mqtt-bridge" },
            enabled: true,
            poll_interval_seconds: 60,
          });
        } catch (saveErr) {
          console.warn("MQTT bridge adapter config save failed", saveErr);
        }
        dispatch({ type: "SET_BACNET_DEVICES", devices: [], selectedDeviceId: null });
        dispatch({
          type: "SET_CONNECTION_STATUS",
          status: "connected",
          message: "MQTT bridge configured — credentials and ACL auto-provisioned",
        });
        return;
      }

      let bacnetDevices: BACnetDevice[] = [];
      if (!isBridge && state.bmsVendor !== 'niagara' && !isMqttBridge && !isMqttDirect) {
        try {
          const bacnetRes = await bmsConnectionApi.testBACnetConnection({
            timeout: 5,
            host: state.host.trim(),
          });
          bacnetDevices = bacnetRes.devices || [];
        } catch (bacErr) {
          console.warn("BACnet discovery skipped or failed for", state.bmsVendor, bacErr);
        }
      }

      let resolvedSiteId = "";
      if (isBridge || state.bmsVendor === 'niagara' || bacnetDevices.length > 0) {
        resolvedSiteId = await ensureSiteCreated();
        const selectedDeviceId = state.bmsVendor === 'niagara' || isBridge ? null : pickDefaultDeviceId(bacnetDevices, state.host);
        dispatch({ type: "SET_BACNET_DEVICES", devices: bacnetDevices, selectedDeviceId });
        dispatch({
          type: "SET_CONNECTION_STATUS",
          status: "connected",
          message: isBridge ? "Bridge connection ready" : state.bmsVendor === 'niagara' ? "oBIX connection successful" : buildConnectionMessage(bacnetDevices, selectedDeviceId),
        });
      } else {
        dispatch({ type: "SET_BACNET_DEVICES", devices: [], selectedDeviceId: null });
        dispatch({
          type: "SET_CONNECTION_STATUS",
          status: "failed",
          message:
            "No BACnet devices matched this host. Check the controller IP, BACnet routing, and UDP port 47808.",
        });
        return;
      }
      try {
        const capabilities = await bmsConnectionApi.getSimbiotCapabilities({
          site_id: resolvedSiteId,
          bms_vendor: state.bmsVendor,
          host: state.host.trim(),
          port: safePort,
          commissioning: true,
          ...(state.username && { username: state.username }),
          ...(state.password && { password: state.password }),
        });
        dispatch({ type: "SET_CAPABILITIES", summary: capabilities.summary, details: capabilities, error: null });
      } catch (capErr) {
        dispatch({
          type: "SET_CAPABILITIES",
          summary: null,
          error: capErr instanceof Error ? capErr.message : "Could not load capabilities",
        });
      }

      // Persist per-site adapter config so the backend can reconnect later.
      try {
        const adapterProtocol = resolveSimbiotProtocol(state.bmsVendor);
        const adapterConfig = isBridge
          ? { base_url: `http://${state.host.trim()}:${safePort}`, token: state.password || state.username || "" }
          : {
              host: state.host.trim(),
              port: safePort,
              ...(state.username && { username: state.username }),
              ...(state.password && { password: state.password }),
              use_https: state.useHttps,
              bms_vendor: state.bmsVendor,
            };
        await bmsConnectionApi.saveSimbiotAdapterConfig({
          site_id: resolvedSiteId,
          protocol: adapterProtocol,
          config: adapterConfig,
          enabled: true,  // New sites: bridge on so phased pipeline progresses
          poll_interval_seconds: 300,
        });
        console.log("Saved adapter config for", resolvedSiteId);
      } catch (saveErr) {
        console.warn("Failed to save adapter config for", resolvedSiteId, saveErr);
      }
    } catch (err) {
      dispatch({
        type: "SET_CONNECTION_STATUS",
        status: "failed",
        message: err instanceof Error ? err.message : "Connection failed",
      });
    }
  }, [buildConnectionMessage, ensureSiteCreated, usesObix, pickDefaultDeviceId, state.bmsVendor, state.host, state.password, state.port, state.requestedSiteId, state.siteName, state.useHttps, state.username]);

  // ---------- CSV Upload ----------
  const handleCsvUpload = useCallback(async () => {
    if (!state.csvFile) {
      dispatch({ type: "SET_ERROR", error: "Select a CSV file first" });
      return;
    }
    if (!state.csvFile.name.endsWith(".csv")) {
      dispatch({ type: "SET_ERROR", error: "File must be a CSV (.csv extension)" });
      return;
    }
    if (!state.siteName.trim()) {
      dispatch({ type: "SET_ERROR", error: "Enter a site name before uploading" });
      return;
    }
    dispatch({ type: "SET_LOADING", loading: true });
    dispatch({ type: "SET_ERROR", error: null });

    try {
      const siteId = await ensureSiteCreated();
      const result = await bmsConnectionApi.discoverFromCsv(siteId, state.csvFile, state.siteName);
      dispatch({
        type: "SET_CSV_UPLOAD_RESULT",
        discoveryId: result.discovery_id,
        summary: {
          discovery_id: result.discovery_id,
          points_count: result.points_count,
          equipment_count: result.equipment_count,
          status: result.status,
          summary: result.summary as Record<string, string | number | boolean>,
        },
      });
    } catch (err) {
      dispatch({
        type: "SET_ERROR",
        error: err instanceof Error ? err.message : "CSV upload failed",
      });
    }
  }, [state.csvFile, state.siteName, ensureSiteCreated]);

  // ---------- Step 2: Discover & Classify ----------
  const handleDiscover = useCallback(async (forceRefresh = false, siteIdOverride?: string) => {
    const resolvedSiteId = siteIdOverride || state.siteId || normalizeRequestedSiteId(state.requestedSiteId);
    if (!resolvedSiteId || !isValidRequestedSiteId(resolvedSiteId)) {
      dispatch({ type: "SET_ERROR", error: "Create or select the site before starting discovery" });
      return;
    }
    if (!state.siteId) {
      dispatch({ type: "SET_FIELD", field: "siteId", value: resolvedSiteId });
    }

    // CSV mode: data already loaded from upload
    if (state.connectionMethod === "csv" && state.discoveryId) {
      dispatch({ type: "SET_DISCOVERY_PHASE", phase: 4 });
      await new Promise(r => setTimeout(r, 300));
      dispatch({ type: "SET_DISCOVERY_PHASE", phase: 0 });
      return;
    }

    const usesDirectCapabilities = state.bmsVendor === 'bridge' || state.bmsVendor === 'niagara' || state.bmsVendor === 'mqtt-bridge' || state.bmsVendor === 'mqtt-direct';
    if (state.selectedDeviceId == null && !usesDirectCapabilities) {
      dispatch({ type: "SET_ERROR", error: "Select the BACnet device to ingest before discovery" });
      return;
    }
    dispatch({ type: "SET_LOADING", loading: true });
    dispatch({ type: "SET_ERROR", error: null });
    dispatch({ type: "SET_DISCOVERY_PHASE", phase: 1 }); // Connecting...

    try {
      await new Promise(r => setTimeout(r, 500));
      dispatch({ type: "SET_DISCOVERY_PHASE", phase: 2 }); // Scanning points...

      await new Promise(r => setTimeout(r, 800));
      dispatch({ type: "SET_DISCOVERY_PHASE", phase: 3 }); // Classifying equipment...

      if (usesDirectCapabilities) {
        // Bridge/oBIX: re-fetch capabilities if state was lost (e.g. page refresh)
        const usesObixNow = state.bmsVendor === 'niagara';
        const bridgePort = usesObixNow ? 80 : state.bmsVendor === 'bridge' ? 8080 : 47808;
        const discPort = Number(state.port);
        const discSafePort = state.port && Number.isFinite(discPort) && discPort > 0 && discPort <= 65535 ? discPort : bridgePort;
        let cap = forceRefresh ? null : state.capabilitySummary;
        let details = forceRefresh ? null : state.capabilityDetails;
        if (!details) {
          try {
            const fresh = await bmsConnectionApi.getSimbiotCapabilities({
              site_id: resolvedSiteId,
              bms_vendor: state.bmsVendor,
              host: state.host.trim(),
              port: discSafePort,
              commissioning: true,
              ...(state.username && { username: state.username }),
              ...(state.password && { password: state.password }),
            });
            cap = fresh.summary;
            details = fresh;
            dispatch({ type: "SET_CAPABILITIES", summary: fresh.summary, details: fresh, error: null });
          } catch { /* use defaults */ }
        }
        const directMapping = buildCapabilitiesMapping(details, resolvedSiteId);
        dispatch({
          type: "SET_DISCOVERY",
          id: `discovery-${resolvedSiteId}`,
          summary: {
            site_id: resolvedSiteId,
            discovery_id: `discovery-${resolvedSiteId}`,
            points_count: cap?.points ?? 0,
            equipment_count: directMapping.equipment_count,
            status: "completed",
            summary: {},
          },
        });
      } else {
        const res = await bmsConnectionApi.discoverAndClassify({
          device_ip: state.host,
          site_id: resolvedSiteId,
          device_bacnet_id: state.selectedDeviceId ?? undefined,
          adapter_type: "bacnet",
          bms_vendor: state.bmsVendor,
        });
        dispatch({ type: "SET_DISCOVERY", id: res.discovery_id, summary: res });
      }
      dispatch({ type: "SET_DISCOVERY_PHASE", phase: 4 }); // Grouping into zones...
      await new Promise(r => setTimeout(r, 300));

      dispatch({ type: "SET_DISCOVERY_PHASE", phase: 0 });
    } catch (err) {
      dispatch({
        type: "SET_ERROR",
        error: err instanceof Error ? err.message : "Discovery failed",
      });
      dispatch({ type: "SET_DISCOVERY_PHASE", phase: 0 });
    }
  }, [state.bmsVendor, state.capabilityDetails, state.capabilitySummary, state.connectionMethod, state.discoveryId, state.host, state.password, state.port, state.requestedSiteId, state.selectedDeviceId, state.siteId, state.username]);

  // ---------- Step 3: Load Mappings ----------
  const handleLoadMappings = useCallback(async (forceRefresh = false, siteIdOverride?: string) => {
    const isCsvMode = state.connectionMethod === "csv";
    const usesDirectCapabilities = (state.bmsVendor === 'bridge' || state.bmsVendor === 'niagara' || state.bmsVendor === 'mqtt-bridge' || state.bmsVendor === 'mqtt-direct') && !isCsvMode;
    if (!state.discoveryId && !usesDirectCapabilities) return;
    const resolvedSiteId = siteIdOverride || state.siteId || normalizeRequestedSiteId(state.requestedSiteId);
    if (!resolvedSiteId || !isValidRequestedSiteId(resolvedSiteId)) {
      dispatch({ type: "SET_ERROR", error: "Create or select the site before loading mappings" });
      return;
    }
    if (!state.siteId) {
      dispatch({ type: "SET_FIELD", field: "siteId", value: resolvedSiteId });
    }
    dispatch({ type: "SET_LOADING", loading: true });
    dispatch({ type: "SET_ERROR", error: null });

    try {
      await new Promise(r => setTimeout(r, 500));
      dispatch({ type: "SET_DISCOVERY_PHASE", phase: 2 }); // Scanning points...

      await new Promise(r => setTimeout(r, 800));
      dispatch({ type: "SET_DISCOVERY_PHASE", phase: 3 }); // Classifying equipment...

      if (usesDirectCapabilities) {
        // Bridge/oBIX: no separate mappings endpoint; group the capability point list for review.
        let details = forceRefresh ? null : state.capabilityDetails;
        if (!details) {
          const usesObixNow = state.bmsVendor === 'niagara';
          const defaultPort = usesObixNow ? 80 : state.bmsVendor === 'bridge' ? 8080 : 47808;
          const mappingPort = Number(state.port);
          const safePort = state.port && Number.isFinite(mappingPort) && mappingPort > 0 && mappingPort <= 65535 ? mappingPort : defaultPort;
          try {
            const fresh = await bmsConnectionApi.getSimbiotCapabilities({
              site_id: resolvedSiteId,
              bms_vendor: state.bmsVendor,
              host: state.host.trim(),
              port: safePort,
              commissioning: true,
              ...(state.username && { username: state.username }),
              ...(state.password && { password: state.password }),
            });
            details = fresh;
            dispatch({ type: "SET_CAPABILITIES", summary: fresh.summary, details: fresh, error: null });
          } catch { /* mapping fallback below will show a single review card */ }
        }
        dispatch({
          type: "SET_MAPPINGS",
          mappings: buildCapabilitiesMapping(details, resolvedSiteId),
        });
      } else {
        const res = await bmsConnectionApi.getMappings(state.discoveryId || "");
        dispatch({ type: "SET_MAPPINGS", mappings: res });
      }
    } catch (err) {
      dispatch({
        type: "SET_ERROR",
        error: err instanceof Error ? err.message : "Failed to load mappings",
      });
    }
  }, [state.discoveryId, state.bmsVendor, state.capabilityDetails, state.connectionMethod, state.host, state.password, state.port, state.requestedSiteId, state.siteId, state.username]);

  // ---------- Step 4: Approve ----------
  const handleApprove = useCallback(async () => {
    if (!state.discoveryId) return;
    dispatch({ type: "SET_APPROVE_STATUS", status: "approving" });

    const isCsvMode = state.connectionMethod === "csv";
    const usesDirectCapabilities = (state.bmsVendor === 'bridge' || state.bmsVendor === 'niagara' || state.bmsVendor === 'mqtt-bridge' || state.bmsVendor === 'mqtt-direct') && !isCsvMode;
    const processingEnabledAfterApproval = false;
    dispatch({ type: "SET_LOADING", loading: true });
    dispatch({ type: "SET_ERROR", error: null });

    try {
      let res: NiagaraApproveResponse;
      if (usesDirectCapabilities) {
        const approvedMappings =
          state.mappings || buildCapabilitiesMapping(state.capabilityDetails, state.siteId);
        const bridgeCommit = await bmsConnectionApi.commitBridgeReviewMappings(
          state.siteId,
          approvedMappings,
          state.approvedBy,
          state.capabilityDetails?.discovery_id,
        );
        let canonicalizationSummary: OnboardingCanonicalizationSummary | undefined;
        let hierarchySummary: OnboardingHierarchySummary | undefined;
        if (state.siteId) {
          canonicalizationSummary = await bmsConnectionApi.canonicalizeOnboardingEquipment(state.siteId, true);
          try {
            hierarchySummary = await bmsConnectionApi.ingestOnboardingHierarchy(state.siteId, true, true);
          } catch (err) {
            hierarchySummary = {
              site_id: state.siteId,
              site_uuid: "",
              commit: true,
              available: false,
              source: null,
              nodes_total: 0,
              relationships_total: 0,
              equipment_relationships_upserted: 0,
              zone_relationships_upserted: 0,
              relationships_skipped: 0,
              review_status_counts: {},
              error: err instanceof Error ? err.message : "Hierarchy ingestion failed",
            };
          }
          await api.toggleSiteProcessing(state.siteId, processingEnabledAfterApproval);
        }
        res = {
          success: true,
          message: `Site approved; ${bridgeCommit.equipment_total} equipment and ${bridgeCommit.points_mapped} points committed. Processing remains disabled.`,
          equipment_created: bridgeCommit.equipment_created,
          canonicalization_summary: canonicalizationSummary,
          hierarchy_summary: hierarchySummary,
        };
      } else {
        res = await bmsConnectionApi.approveMappings(
          state.discoveryId,
          state.approvedBy,
        );
        if (res.success && state.siteId) {
          try {
            res.hierarchy_summary = await bmsConnectionApi.ingestOnboardingHierarchy(state.siteId, true, true);
          } catch (err) {
            res.hierarchy_summary = {
              site_id: state.siteId,
              site_uuid: "",
              commit: true,
              available: false,
              source: null,
              nodes_total: 0,
              relationships_total: 0,
              equipment_relationships_upserted: 0,
              zone_relationships_upserted: 0,
              relationships_skipped: 0,
              review_status_counts: {},
              error: err instanceof Error ? err.message : "Hierarchy ingestion failed",
            };
          }
          await api.toggleSiteProcessing(state.siteId, processingEnabledAfterApproval);
        }
      }
      dispatch({
        type: "SET_APPROVE_STATUS",
        status: res.success ? "approved" : "failed",
        message: res.message,
        result: {
          equipment_created: res.equipment_created,
          canonicalization_summary: res.canonicalization_summary,
          hierarchy_summary: res.hierarchy_summary,
        },
      });

      if (res.success) {
        setTimeout(() => {
          if (usesDirectCapabilities) {
            dispatch({ type: "SET_STEP", step: 5 });
          } else {
            dispatch({ type: "SET_VERIFICATION_WIZARD", show: true });
          }
        }, 800);
      }
    } catch (err) {
      dispatch({
        type: "SET_APPROVE_STATUS",
        status: "failed",
        message: err instanceof Error ? err.message : "Approval failed",
      });
    }
  }, [
    state.approvedBy,
    state.bmsVendor,
    state.capabilityDetails,
    state.connectionMethod,
    state.discoveryId,
    state.mappings,
    state.siteId,
  ]);

  // ---------- Step navigation ----------
  const goNext = useCallback(async () => {
    const nextStep = state.step + 1;
    if (nextStep > 6) {
      onComplete(state.siteId || state.requestedSiteId);
      return;
    }
    dispatch({ type: "SET_STEP", step: nextStep });

    if (nextStep === 2) {
      await handleDiscover();
    } else if (nextStep === 3) {
      await handleLoadMappings();
    }
  }, [state.step, state.siteId, state.requestedSiteId, handleDiscover, handleLoadMappings, onComplete]);

  const goBack = useCallback(() => {
    dispatch({ type: "SET_STEP", step: Math.max(1, state.step - 1) });
  }, [state.step]);

  const handleRediscover = useCallback(async () => {
    const resolvedSiteId = state.siteId || normalizeRequestedSiteId(state.requestedSiteId);
    dispatch({ type: "RESET_DISCOVERY_REVIEW" });
    await handleDiscover(true, resolvedSiteId);
  }, [handleDiscover, state.requestedSiteId, state.siteId]);

  const handleRescanReview = useCallback(async () => {
    const resolvedSiteId = state.siteId || normalizeRequestedSiteId(state.requestedSiteId);
    await handleDiscover(true, resolvedSiteId);
    await handleLoadMappings(true, resolvedSiteId);
  }, [handleDiscover, handleLoadMappings, state.requestedSiteId, state.siteId]);

  const canGoNext = (): boolean => {
    switch (state.step) {
      case 1:
        if (state.connectionMethod === "csv") {
          return state.connectionStatus === "connected" && !!state.siteId && !!state.discoveryId;
        }
        return (
          state.connectionStatus === "connected" &&
          !!state.siteId &&
          (state.selectedDeviceId !== null || state.bmsVendor === 'niagara' || state.bmsVendor === 'bridge' || state.bmsVendor === 'mqtt-bridge' || state.bmsVendor === 'mqtt-direct')
        );
      case 2:
        return !!state.discoveryId && !state.loading;
      case 3:
        return !!state.mappings && !state.loading;
      case 4:
        return state.approveStatus !== "idle";
      case 5:
        return state.tenantAccessConfirmed;
      case 6:
        return true;
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
          {sites.length > 0 && (
            <div className="col-span-2 sm:col-span-1">
              <label className="block text-sm font-medium mb-1" style={labelStyle}>
                Saved Site
              </label>
              <select
                value={sites.some((site) => normalizeRequestedSiteId(site.code || site.id) === state.requestedSiteId) ? state.requestedSiteId : ""}
                onChange={(e) => {
                  if (!e.target.value) return;
                  void handleLoadSavedSite(e.target.value);
                }}
                className="w-full rounded px-3 py-2 text-sm"
                style={inputStyle}
              >
                <option value="">Select saved site...</option>
                {sites.map((site) => {
                  const code = normalizeRequestedSiteId(site.code || site.id);
                  return (
                    <option key={site.id || code} value={code}>
                      {code} — {site.name}
                    </option>
                  );
                })}
              </select>
            </div>
          )}

          <div className="col-span-2 sm:col-span-1">
            <label className="block text-sm font-medium mb-1" style={labelStyle}>
              Site Code
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={state.requestedSiteId}
                onChange={(e) =>
                  dispatch({
                    type: "SET_FIELD",
                    field: "requestedSiteId",
                    value: e.target.value,
                  })
                }
                placeholder="site-005"
                className="flex-1 rounded px-3 py-2 text-sm"
                style={inputStyle}
              />
              <button
                type="button"
                onClick={() => void handleLoadSavedSite()}
                disabled={state.savedSiteLoading}
                className="px-3 py-2 rounded text-sm font-medium transition-colors flex items-center gap-2"
                style={{
                  background: "var(--color-sentinel-bg-primary)",
                  border: "1px solid var(--color-sentinel-border)",
                  color: "var(--color-sentinel-text-primary)",
                  opacity: state.savedSiteLoading ? 0.7 : 1,
                }}
              >
                {state.savedSiteLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                Load
              </button>
            </div>
            {state.savedSiteMessage && (
              <p className="mt-1 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {state.savedSiteMessage}
              </p>
            )}
          </div>

          {/* Site Name */}
          <div className="col-span-2 sm:col-span-1">
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

          <div className="col-span-2">
            <button
              type="button"
              onClick={handleScrapeOnboardingFacts}
              disabled={state.onboardingFactsLoading || (!state.siteName.trim() && !state.siteAddress.trim())}
              className="inline-flex items-center gap-2 px-3 py-2 rounded text-sm font-medium transition-opacity disabled:opacity-50"
              style={{
                background: "var(--color-sentinel-bg-primary)",
                border: "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-primary)",
              }}
            >
              {state.onboardingFactsLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Search className="w-4 h-4" />
              )}
              Prefill From Web
            </button>
            {state.onboardingFactsMessage && (
              <p className="text-xs mt-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {state.onboardingFactsMessage}
              </p>
            )}
            {state.onboardingFactsMissing.length > 0 && (
              <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-amber)" }}>
                Manual: {state.onboardingFactsMissing.join(", ")}
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
              onChange={(e) => {
                const nextType = e.target.value;
                const hospital = isHospitalType(nextType);
                dispatch({
                  type: "SET_FIELD",
                  field: "siteType",
                  value: nextType,
                });
                dispatch({ type: "SET_FIELD", field: "siteOperates24_7", value: hospital });
                dispatch({ type: "SET_FIELD", field: "clinicalZonesPresent", value: hospital });
              }}
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

          <div className="col-span-2 sm:col-span-1">
            <label className="block text-sm font-medium mb-1" style={labelStyle}>
              Year Built
            </label>
            <input
              type="number"
              value={state.yearBuilt || ""}
              onChange={(e) => dispatch({ type: "SET_FIELD", field: "yearBuilt", value: parseWizardNumber(e.target.value) })}
              className="w-full rounded px-3 py-2 text-sm"
              style={inputStyle}
            />
          </div>

          <div className="col-span-2 sm:col-span-1">
            <label className="block text-sm font-medium mb-1" style={labelStyle}>
              Occupancy Capacity
            </label>
            <input
              type="number"
              value={state.occupancyCapacity || ""}
              onChange={(e) => dispatch({ type: "SET_FIELD", field: "occupancyCapacity", value: parseWizardNumber(e.target.value) })}
              className="w-full rounded px-3 py-2 text-sm"
              style={inputStyle}
            />
          </div>

          <div className="col-span-2 sm:col-span-1">
            <label className="block text-sm font-medium mb-1" style={labelStyle}>
              Desks / Workpoints
            </label>
            <input
              type="number"
              value={state.totalDesks || ""}
              onChange={(e) => dispatch({ type: "SET_FIELD", field: "totalDesks", value: parseWizardNumber(e.target.value) })}
              className="w-full rounded px-3 py-2 text-sm"
              style={inputStyle}
            />
          </div>

          <div className="col-span-2 sm:col-span-1">
            <label className="block text-sm font-medium mb-1" style={labelStyle}>
              Parking Bays
            </label>
            <input
              type="number"
              value={state.parkingBays || ""}
              onChange={(e) => dispatch({ type: "SET_FIELD", field: "parkingBays", value: parseWizardNumber(e.target.value) })}
              className="w-full rounded px-3 py-2 text-sm"
              style={inputStyle}
            />
          </div>

          <div className="col-span-2 sm:col-span-1">
            <label className="block text-sm font-medium mb-1" style={labelStyle}>
              Electricity Provider
            </label>
            <input
              type="text"
              value={state.electricityProvider}
              onChange={(e) => dispatch({ type: "SET_FIELD", field: "electricityProvider", value: e.target.value })}
              placeholder="City Power, Eskom, eThekwini"
              className="w-full rounded px-3 py-2 text-sm"
              style={inputStyle}
            />
          </div>

          <div className="col-span-2 sm:col-span-1">
            <label className="block text-sm font-medium mb-1" style={labelStyle}>
              NMD Limit (kVA)
            </label>
            <input
              type="number"
              value={state.nmdLimitKva || ""}
              onChange={(e) => dispatch({ type: "SET_FIELD", field: "nmdLimitKva", value: parseWizardNumber(e.target.value) })}
              className="w-full rounded px-3 py-2 text-sm"
              style={inputStyle}
            />
          </div>

          <div className="col-span-2 sm:col-span-1">
            <label className="block text-sm font-medium mb-1" style={labelStyle}>
              Demand Charge (per kVA)
            </label>
            <input
              type="number"
              value={state.demandChargePerKva || ""}
              onChange={(e) => dispatch({ type: "SET_FIELD", field: "demandChargePerKva", value: parseWizardNumber(e.target.value) })}
              className="w-full rounded px-3 py-2 text-sm"
              style={inputStyle}
            />
          </div>

          <div className="col-span-2 grid grid-cols-1 sm:grid-cols-3 gap-3">
            <label className="flex items-center gap-2 text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
              <input
                type="checkbox"
                checked={state.siteOperates24_7}
                onChange={(e) => dispatch({ type: "SET_FIELD", field: "siteOperates24_7", value: e.target.checked })}
              />
              24/7 operation
            </label>
            <label className="flex items-center gap-2 text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
              <input
                type="checkbox"
                checked={state.saturdayActive}
                disabled={state.siteOperates24_7}
                onChange={(e) => dispatch({ type: "SET_FIELD", field: "saturdayActive", value: e.target.checked })}
              />
              Saturday occupied
            </label>
            <label className="flex items-center gap-2 text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
              <input
                type="checkbox"
                checked={state.sundayActive}
                disabled={state.siteOperates24_7}
                onChange={(e) => dispatch({ type: "SET_FIELD", field: "sundayActive", value: e.target.checked })}
              />
              Sunday occupied
            </label>
          </div>

          {!state.siteOperates24_7 && (
            <>
              <div className="col-span-2 sm:col-span-1">
                <label className="block text-sm font-medium mb-1" style={labelStyle}>
                  Weekday Open
                </label>
                <input
                  type="time"
                  value={state.weekdayStart}
                  onChange={(e) => dispatch({ type: "SET_FIELD", field: "weekdayStart", value: e.target.value })}
                  className="w-full rounded px-3 py-2 text-sm"
                  style={inputStyle}
                />
              </div>
              <div className="col-span-2 sm:col-span-1">
                <label className="block text-sm font-medium mb-1" style={labelStyle}>
                  Weekday Close
                </label>
                <input
                  type="time"
                  value={state.weekdayEnd}
                  onChange={(e) => dispatch({ type: "SET_FIELD", field: "weekdayEnd", value: e.target.value })}
                  className="w-full rounded px-3 py-2 text-sm"
                  style={inputStyle}
                />
              </div>
            </>
          )}

          {isHospitalType(state.siteType) && (
            <label className="col-span-2 flex items-center gap-2 text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
              <input
                type="checkbox"
                checked={state.clinicalZonesPresent}
                onChange={(e) => dispatch({ type: "SET_FIELD", field: "clinicalZonesPresent", value: e.target.checked })}
              />
              Clinical zones present
            </label>
          )}
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

        {/* Connection method toggle */}
        <div className="flex gap-2 mb-4">
          <button
            type="button"
            onClick={() => dispatch({ type: "SET_FIELD", field: "connectionMethod", value: "network" })}
            className="flex items-center gap-2 px-3 py-2 rounded text-sm font-medium transition-colors"
            style={{
              background: state.connectionMethod === "network" ? "var(--color-sentinel-blue)" : "var(--color-sentinel-bg-primary)",
              color: "#fff",
              border: state.connectionMethod === "network" ? "none" : "1px solid var(--color-sentinel-border)",
              opacity: state.connectionMethod === "network" ? 1 : 0.7,
            }}
          >
            <Search className="w-4 h-4" />
            Auto-discover (BACnet/IP)
          </button>
          <button
            type="button"
            onClick={() => dispatch({ type: "SET_FIELD", field: "connectionMethod", value: "csv" })}
            className="flex items-center gap-2 px-3 py-2 rounded text-sm font-medium transition-colors"
            style={{
              background: state.connectionMethod === "csv" ? "var(--color-sentinel-blue)" : "var(--color-sentinel-bg-primary)",
              color: "#fff",
              border: state.connectionMethod === "csv" ? "none" : "1px solid var(--color-sentinel-border)",
              opacity: state.connectionMethod === "csv" ? 1 : 0.7,
            }}
          >
            <ClipboardCheck className="w-4 h-4" />
            Upload CSV export
          </button>
        </div>

        {/* Network discovery mode */}
        {state.connectionMethod === "network" && (
          <>
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
                  onChange={(e) => {
                    const raw = e.target.value;
                    if (raw === "") {
                      dispatch({ type: "SET_FIELD", field: "port", value: "" });
                      return;
                    }
                    const parsed = parseInt(raw, 10);
                    if (Number.isFinite(parsed)) {
                      dispatch({ type: "SET_FIELD", field: "port", value: Math.min(Math.max(parsed, 1), 65535) });
                    }
                  }}
                  className="w-full rounded px-3 py-2 text-sm"
                  style={inputStyle}
                />
              </div>
              <div className="col-span-2 sm:col-span-1">
                <label className="block text-sm font-medium mb-1 flex items-center gap-2" style={labelStyle}>
                  <span>Username / API Key</span>
                  <Tooltip content="Optional credential for BMS or bridge authentication. Required if your BMS or gateway requires login.">
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
                  <span>Password / Token</span>
                  <Tooltip content="Optional credential or API token for BMS or bridge authentication. Encrypted and never stored in logs.">
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
              {usesObix && (
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
            {!usesObix && (
              <div
                className="p-3 rounded text-sm mt-4"
                style={{
                  background: "var(--color-sentinel-bg-primary)",
                  border: "1px solid var(--color-sentinel-border)",
                  color: "var(--color-sentinel-text-secondary)",
                }}
              >
                Credentials are optional for {vendorLabel}. SENTINEL will verify BACnet connectivity,
                list matching controllers for the host you entered, and use your selected device for discovery.
              </div>
            )}
          </>
        )}

        {/* CSV upload mode */}
        {state.connectionMethod === "csv" && (
          <div className="space-y-4">
            <div
              className="p-4 rounded text-sm"
              style={{
                background: "var(--color-sentinel-bg-primary)",
                border: "2px dashed var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-secondary)",
              }}
            >
              <p className="mb-3">
                Upload a BMS point list CSV export. The system will parse the file, extract
                equipment IDs from hierarchical naming, and classify points using AI.
              </p>
              <p className="text-xs mb-3" style={{ opacity: 0.7 }}>
                Expected format: name, object_type, instance, units, present_value, description, min_value, max_value, writable
              </p>
              <input
                type="file"
                accept=".csv"
                onChange={(e) => {
                  const file = e.target.files?.[0] ?? null;
                  dispatch({ type: "SET_FIELD", field: "csvFile", value: file });
                }}
                className="block w-full text-sm file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-medium hover:file:cursor-pointer"
                style={{
                  color: "var(--color-sentinel-text-secondary)",
                }}
              />
            </div>
            <button
              onClick={handleCsvUpload}
              disabled={state.loading || !state.siteName.trim() || !state.csvFile}
              className="flex items-center gap-2 px-4 py-2 rounded text-sm font-medium transition-opacity disabled:opacity-50"
              style={{
                background: "var(--color-sentinel-blue)",
                color: "#fff",
              }}
            >
              {state.loading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Upload className="w-4 h-4" />
              )}
              Upload &amp; Classify
            </button>
          </div>
        )}
      </div>

      {/* Network: Test connection / CSV: Success result */}
      {state.connectionMethod === "network" && (
        <>
          <button
            onClick={handleTestConnection}
            disabled={
              state.connectionStatus === "testing" ||
              !state.siteName.trim() ||
              (state.bmsVendor !== 'mqtt-bridge' && !state.host.trim())
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
        </>
      )}

      {/* CSV upload result */}
      {state.connectionMethod === "csv" && state.connectionStatus === "connected" && (
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

      {state.connectionMethod === "csv" && state.error && (
        <div
          className="flex items-start gap-2 p-3 rounded text-sm"
          style={{
            background: "var(--color-sentinel-red)11",
            border: "1px solid var(--color-sentinel-red)",
            color: "var(--color-sentinel-red)",
          }}
        >
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>{state.error}</span>
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
          {state.connectionMethod === "csv"
            ? "CSV points parsed and classified into equipment groups using Brick Schema ontology."
            : "AI is scanning BACnet points and classifying them into equipment groups using Brick Schema ontology."}
        </p>
      </div>

      {/* Help section */}
      <HelpSection title="What's Happening" variant="info">
        {state.connectionMethod === "csv"
          ? "SENTINEL has parsed your CSV export, extracted hierarchical equipment IDs from point names, and classified each point using Haystack/Brick ontology. The results below show what was found."
          : "SENTINEL is discovering BACnet points from your BMS and using AI to classify them into equipment groups. This involves connecting to the BMS, scanning available points, and analyzing their names and characteristics to infer equipment types and zones."}
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
              onClick={() => void handleDiscover()}
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

          <button
            type="button"
            onClick={() => void handleRediscover()}
            disabled={state.loading}
            className="flex items-center gap-2 px-3 py-2 rounded text-sm font-medium transition-opacity disabled:opacity-50"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          >
            {state.loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            Rediscover Points
          </button>

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

      <div
        className="flex flex-wrap items-center gap-3 rounded p-3"
        style={{
          background: "var(--color-sentinel-bg-secondary)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <button
          type="button"
          onClick={() => void handleRescanReview()}
          disabled={state.loading}
          className="flex items-center gap-2 px-4 py-2 rounded text-sm font-semibold transition-opacity disabled:opacity-50"
          style={{
            background: "var(--color-sentinel-blue)",
            color: "#fff",
            border: "1px solid var(--color-sentinel-blue)",
            cursor: state.loading ? "not-allowed" : "pointer",
          }}
        >
          {state.loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
          {state.loading ? "Rescanning..." : "Rescan & Reload Review"}
        </button>
        <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Refetches bridge capabilities and reruns grouping/classification.
        </span>
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
              onClick={() => void handleLoadMappings()}
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

          {/* Unclassified equipment banner */}
          {state.mappings.equipment.filter((eq) => eq.equipment_type === "unknown").length > 0 && (
            <div
              className="flex items-center gap-2 p-3 rounded text-sm"
              style={{
                background: "var(--color-sentinel-red)11",
                border: "1px solid var(--color-sentinel-red)",
                color: "var(--color-sentinel-red)",
              }}
            >
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>
                {state.mappings.equipment.filter((eq) => eq.equipment_type === "unknown").length} equipment
                have unclassified types — manual classification required before approval
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
                          {eq.equipment_type === "unknown" && (
                            <span
                              className="text-xs px-2 py-0.5 rounded font-medium"
                              style={{
                                background: "var(--color-sentinel-amber)22",
                                color: "var(--color-sentinel-amber)",
                                border: "1px solid var(--color-sentinel-amber)44",
                              }}
                            >
                              <AlertTriangle className="w-3 h-3 inline mr-1" />
                              Unclassified type
                            </span>
                          )}
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
          {state.approveResult?.canonicalization_summary && (
            <div
              className="w-full max-w-xl rounded p-4 text-left space-y-3"
              style={{
                background: state.approveResult.canonicalization_summary.error
                  ? "var(--color-sentinel-red)11"
                  : "var(--color-sentinel-bg-secondary)",
                border: state.approveResult.canonicalization_summary.error
                  ? "1px solid var(--color-sentinel-red)"
                  : "1px solid var(--color-sentinel-border)",
              }}
            >
              <div className="flex items-center justify-between gap-3">
                <h5
                  className="text-sm font-semibold"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  Canonicalization
                </h5>
                <span
                  className="text-xs px-2 py-1 rounded"
                  style={{
                    background: "var(--color-sentinel-blue)22",
                    color: "var(--color-sentinel-blue)",
                  }}
                >
                  {state.approveResult.canonicalization_summary.commit ? "Applied" : "Preview"}
                </span>
              </div>
              {state.approveResult.canonicalization_summary.error ? (
                <p className="text-sm" style={{ color: "var(--color-sentinel-red)" }}>
                  {state.approveResult.canonicalization_summary.error}
                </p>
              ) : (
                <>
                  <div className="grid grid-cols-3 gap-2">
                    <SummaryCard
                      label="Canonicalized"
                      value={state.approveResult.canonicalization_summary.equipment_canonicalized}
                      color="var(--color-sentinel-green)"
                    />
                    <SummaryCard
                      label="Needs Review"
                      value={state.approveResult.canonicalization_summary.needs_review ?? "—"}
                      color={
                        (state.approveResult.canonicalization_summary.needs_review ?? 0) > 0
                          ? "var(--color-sentinel-amber)"
                          : "var(--color-sentinel-green)"
                      }
                    />
                    <SummaryCard
                      label="Zones Added"
                      value={state.approveResult.canonicalization_summary.zone_proposals_count}
                      color="var(--color-sentinel-blue)"
                    />
                  </div>
                  {(state.approveResult.canonicalization_summary.needs_review ?? 0) > 0 && (
                    <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      Remaining items stay in review until their equipment type, zone, or plant policy is confirmed.
                    </p>
                  )}
                </>
              )}
            </div>
          )}
          {state.approveResult?.hierarchy_summary && (
            <div
              className="w-full max-w-xl rounded p-4 text-left space-y-3"
              style={{
                background: state.approveResult.hierarchy_summary.error
                  ? "var(--color-sentinel-red)11"
                  : "var(--color-sentinel-bg-secondary)",
                border: state.approveResult.hierarchy_summary.error
                  ? "1px solid var(--color-sentinel-red)"
                  : "1px solid var(--color-sentinel-border)",
              }}
            >
              <div className="flex items-center justify-between gap-3">
                <h5
                  className="text-sm font-semibold"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  BMS Hierarchy
                </h5>
                <span
                  className="text-xs px-2 py-1 rounded"
                  style={{
                    background: state.approveResult.hierarchy_summary.available
                      ? "var(--color-sentinel-green)22"
                      : "var(--color-sentinel-amber)22",
                    color: state.approveResult.hierarchy_summary.available
                      ? "var(--color-sentinel-green)"
                      : "var(--color-sentinel-amber)",
                  }}
                >
                  {state.approveResult.hierarchy_summary.available ? "Imported" : "Unavailable"}
                </span>
              </div>
              {state.approveResult.hierarchy_summary.error ? (
                <p className="text-sm" style={{ color: "var(--color-sentinel-red)" }}>
                  {state.approveResult.hierarchy_summary.error}
                </p>
              ) : state.approveResult.hierarchy_summary.available ? (
                <>
                  <div className="grid grid-cols-3 gap-2">
                    <SummaryCard
                      label="Equipment Links"
                      value={state.approveResult.hierarchy_summary.equipment_relationships_upserted}
                      color="var(--color-sentinel-green)"
                    />
                    <SummaryCard
                      label="Zone Links"
                      value={state.approveResult.hierarchy_summary.zone_relationships_upserted}
                      color="var(--color-sentinel-blue)"
                    />
                    <SummaryCard
                      label="Skipped"
                      value={state.approveResult.hierarchy_summary.relationships_skipped}
                      color={
                        state.approveResult.hierarchy_summary.relationships_skipped > 0
                          ? "var(--color-sentinel-amber)"
                          : "var(--color-sentinel-green)"
                      }
                    />
                  </div>
                  <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Source: {state.approveResult.hierarchy_summary.source || "BMS hierarchy"}
                  </p>
                </>
              ) : (
                <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {state.approveResult.hierarchy_summary.message ||
                    "No native hierarchy was provided by the BMS adapter. Manual mapping remains the fallback."}
                </p>
              )}
            </div>
          )}
          <button
            onClick={() => {
              dispatch({ type: "SET_STEP", step: 5 });
            }}
            className="px-6 py-2 rounded text-sm font-medium mt-2"
            style={{
              background: "var(--color-sentinel-green)",
              color: "#fff",
            }}
          >
            Continue to Tenant Access
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
                {state.bmsVendor === 'bridge' ? (
                  <div className="flex items-center gap-2">
                    <span style={{ color: "var(--color-sentinel-green)" }}>✓</span>
                    <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                      Bridge-connected site — equipment mapped via bridge API
                    </span>
                  </div>
                ) : (
                  <>
                <div className="flex items-center gap-2">
                  {(() => {
                    const unclassifiedCount = state.mappings?.equipment?.filter(
                      (eq) => eq.equipment_type === "unknown"
                    ).length ?? 0;
                    const allClassified = unclassifiedCount === 0;
                    return (
                      <>
                        <span
                          style={{
                            color: allClassified
                              ? "var(--color-sentinel-green)"
                              : "var(--color-sentinel-red)",
                          }}
                        >
                          {allClassified ? "✓" : "⚠️"}
                        </span>
                        <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                          {allClassified
                            ? "All equipment types correctly identified"
                            : `${unclassifiedCount} equipment type${unclassifiedCount !== 1 ? "s" : ""} unclassified — fix before approving`}
                        </span>
                      </>
                    );
                  })()}
                </div>
                <div className="flex items-center gap-2">
                  <span style={{ color: "var(--color-sentinel-green)" }}>✓</span>
                  <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                    Equipment IDs converted to SENTINEL canonical codes
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span style={{ color: "var(--color-sentinel-green)" }}>✓</span>
                  <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                    Zones auto-assigned from equipment locations
                  </span>
                </div>
                  </>
                )}
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

  // ============= Step 5: Tenant Access =============
  const renderStep5 = () => {
    const shortSiteCode = siteDisplayCode(state.siteId);
    const schemaUrl = `https://bms.sentinel-ai.co.za/api/mcp/openai/openapi.json?site_id=${encodeURIComponent(shortSiteCode)}`;
    const tenantName = state.tenantName.trim() || state.siteName.trim() || shortSiteCode;

    return (
      <div className="space-y-5">
        <div>
          <h3 className="text-lg font-semibold mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Step 5: Tenant MCP Access
          </h3>
          <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Bind this site to a tenant-scoped GPT connector before client sharing.
          </p>
        </div>

        <HelpSection title="Tenant Boundary" variant="warning">
          New sites stay private to onboarding until a tenant key and scoped schema are created. This step records the intended boundary; final key creation remains an admin-controlled deployment action.
        </HelpSection>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div
            className="rounded-lg p-4 space-y-4"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <div className="flex items-center gap-2">
              <KeyRound className="w-5 h-5" style={{ color: "var(--color-sentinel-blue)" }} />
              <h4 className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Tenant Scope
              </h4>
            </div>

            <div>
              <label className="block text-xs font-medium mb-1" style={labelStyle}>
                Tenant / Client Name
              </label>
              <input
                type="text"
                value={state.tenantName}
                onChange={(e) => dispatch({ type: "SET_FIELD", field: "tenantName", value: e.target.value })}
                className="w-full rounded px-3 py-2 text-sm"
                placeholder={state.siteName || "Client name"}
                style={inputStyle}
              />
            </div>

            <div>
              <label className="block text-xs font-medium mb-1" style={labelStyle}>
                Initial Access Mode
              </label>
              <select
                value={state.tenantAccessMode}
                onChange={(e) => dispatch({ type: "SET_FIELD", field: "tenantAccessMode", value: e.target.value })}
                className="w-full rounded px-3 py-2 text-sm"
                style={inputStyle}
              >
                <option value="shadow_readonly">Shadow read-only</option>
                <option value="advisory_readonly">Advisory read-only</option>
                <option value="disabled">Create later</option>
              </select>
            </div>

            <div
              className="rounded p-3 text-sm space-y-2"
              style={{
                background: "var(--color-sentinel-bg-primary)",
                border: "1px solid var(--color-sentinel-border)",
              }}
            >
              <div className="flex justify-between gap-3">
                <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Allowed site</span>
                <span className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  {shortSiteCode}
                </span>
              </div>
              <div className="flex justify-between gap-3">
                <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Tenant</span>
                <span className="font-medium text-right" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  {tenantName}
                </span>
              </div>
              <div className="flex justify-between gap-3">
                <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Write tools</span>
                <span className="font-medium" style={{ color: "var(--color-sentinel-amber)" }}>
                  Disabled
                </span>
              </div>
            </div>
          </div>

          <div
            className="rounded-lg p-4 space-y-4"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <h4 className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
              Connector Package
            </h4>
            <div
              className="rounded p-3 text-xs break-all"
              style={{
                background: "var(--color-sentinel-bg-primary)",
                border: "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-secondary)",
              }}
            >
              {schemaUrl}
            </div>
            <div className="space-y-2 text-sm">
              {[
                `Schema exposes ${shortSiteCode} only`,
                "Tenant key must be deployed separately",
                "Search/fetch remain disabled for tenant-scoped connectors",
                "Promotion from shadow requires manual approval",
              ].map((item) => (
                <div key={item} className="flex items-center gap-2">
                  <CheckCircle className="w-4 h-4 shrink-0" style={{ color: "var(--color-sentinel-green)" }} />
                  <span style={{ color: "var(--color-sentinel-text-primary)" }}>{item}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <label
          className="flex items-start gap-3 rounded-lg p-4 cursor-pointer"
          style={{
            background: "var(--color-sentinel-green)11",
            border: "1px solid var(--color-sentinel-green)44",
          }}
        >
          <input
            type="checkbox"
            checked={state.tenantAccessConfirmed}
            onChange={(e) =>
              dispatch({ type: "SET_FIELD", field: "tenantAccessConfirmed", value: e.target.checked })
            }
            className="mt-1"
          />
          <span className="text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Tenant access boundary recorded for {tenantName}. Do not share this GPT until the scoped key is deployed.
          </span>
        </label>
      </div>
    );
  };

  // ============= Step 6: Configure Site Settings =============
  const renderStep6 = () => {
    const handleSaveContacts = async () => {
      if (!state.siteId) return;
      dispatch({ type: "SET_LOADING", loading: true });
      try {
        await buildingConfigApi.updateConfig(state.siteId, {
          contacts: {
            facility_manager: state.facilityManager,
            email: state.contactEmail,
            emergency: state.contactPhone,
            whatsapp: state.whatsappPhone,
          },
        });
      } catch (e) {
        console.warn("Failed to save contacts", e);
      }
      dispatch({ type: "SET_LOADING", loading: false });
      onComplete(state.siteId || state.requestedSiteId);
    };

    return (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-semibold mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
          Step 6: Configure Site Settings
        </h3>
        <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Your site is connected. Set up contacts and enable data flow, or skip to finish later.
        </p>
      </div>

      <div className="rounded-lg p-4 space-y-4" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--color-sentinel-border)" }}>
        <h4 className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
          Site Contacts
        </h4>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Facility Manager
            </label>
            <input type="text" value={state.facilityManager || ""} onChange={(e) => dispatch({ type: "SET_FIELD", field: "facilityManager", value: e.target.value })} className="w-full rounded px-3 py-2 text-sm" placeholder="Name" style={{ background: "var(--color-sentinel-bg-primary)", border: "1px solid var(--color-sentinel-border)", color: "var(--color-sentinel-text-primary)" }} />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Email
            </label>
            <input type="email" value={state.contactEmail || ""} onChange={(e) => dispatch({ type: "SET_FIELD", field: "contactEmail", value: e.target.value })} className="w-full rounded px-3 py-2 text-sm" placeholder="manager@email.com" style={{ background: "var(--color-sentinel-bg-primary)", border: "1px solid var(--color-sentinel-border)", color: "var(--color-sentinel-text-primary)" }} />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Emergency Phone
            </label>
            <input type="tel" value={state.contactPhone || ""} onChange={(e) => dispatch({ type: "SET_FIELD", field: "contactPhone", value: e.target.value })} className="w-full rounded px-3 py-2 text-sm" placeholder="+27 82 555 0101" style={{ background: "var(--color-sentinel-bg-primary)", border: "1px solid var(--color-sentinel-border)", color: "var(--color-sentinel-text-primary)" }} />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              WhatsApp
            </label>
            <input type="tel" value={state.whatsappPhone || ""} onChange={(e) => dispatch({ type: "SET_FIELD", field: "whatsappPhone", value: e.target.value })} className="w-full rounded px-3 py-2 text-sm" placeholder="+27 82 555 0101" style={{ background: "var(--color-sentinel-bg-primary)", border: "1px solid var(--color-sentinel-border)", color: "var(--color-sentinel-text-primary)" }} />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Technicians / Concierge
            </label>
            <input type="text" value={state.technicianEmails || ""} onChange={(e) => dispatch({ type: "SET_FIELD", field: "technicianEmails", value: e.target.value })} className="w-full rounded px-3 py-2 text-sm" placeholder="Add email addresses" style={{ background: "var(--color-sentinel-bg-primary)", border: "1px solid var(--color-sentinel-border)", color: "var(--color-sentinel-text-primary)" }} />
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--color-sentinel-border)" }}>
        <div>
          <p className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
            SIMBIOT Bridge
          </p>
          <p className="text-xs mt-0.5" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Enable data flow from BMS to SENTINEL
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={state.bridgeDataFlowEnabled}
          onClick={() =>
            dispatch({
              type: "SET_FIELD",
              field: "bridgeDataFlowEnabled",
              value: !state.bridgeDataFlowEnabled,
            })
          }
          className="relative inline-flex h-7 w-14 items-center rounded-full transition-colors"
          style={{
            background: state.bridgeDataFlowEnabled ? "var(--color-sentinel-green)" : "#dc2626",
            border: `1px solid ${state.bridgeDataFlowEnabled ? "var(--color-sentinel-green)" : "#b91c1c"}`,
          }}
        >
          <span
            className="absolute h-5 w-5 rounded-full bg-white shadow transition-transform"
            style={{
              left: 3,
              transform: state.bridgeDataFlowEnabled ? "translateX(28px)" : "translateX(0)",
            }}
          />
          <span className="sr-only">
            {state.bridgeDataFlowEnabled ? "SIMBIOT Bridge data flow active" : "SIMBIOT Bridge data flow inactive"}
          </span>
        </button>
      </div>

      <div className="rounded-lg p-4 space-y-3" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--color-sentinel-border)" }}>
        <h4 className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
          Building Twin
        </h4>
        <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Generate a 3D building model for the cockpit from a web photo of {state.siteName}.
        </p>
          <button
          onClick={async () => {
            dispatch({ type: "SET_LOADING", loading: true });
            try {
              const { getAccessToken } = await import('@/lib/api');
              const token = getAccessToken();
              const resp = await fetch(`/api/sites/${state.siteId}/scrape-geometry`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ site_name: state.siteName, address: state.siteAddress }),
              });
              if (resp.ok) alert("Building twin generated! View it in the Cockpit.");
              else alert("Could not find building photo online.");
            } catch (e) {
              console.warn("Failed to scrape geometry", e);
            }
            dispatch({ type: "SET_LOADING", loading: false });
          }}
          disabled={state.loading}
          className="flex items-center gap-2 px-4 py-2 rounded text-sm font-medium transition-opacity disabled:opacity-50"
          style={{ background: "var(--color-sentinel-blue)", color: "#fff" }}
        >
          {state.loading ? "Searching..." : "Generate Building Twin"}
        </button>
      </div>

      <div className="flex justify-end pt-2">
        <button
          onClick={handleSaveContacts}
          className="flex items-center gap-2 px-5 py-2 rounded text-sm font-medium"
          style={{ background: "var(--color-sentinel-green)", color: "#fff" }}
        >
          <CheckCircle className="w-4 h-4" />
          Finish Onboarding
        </button>
      </div>
    </div>
    );
  };

  // ============= Main Render =============

  const stepRenderers = [renderStep1, renderStep2, renderStep3, renderStep4, renderStep5, renderStep6];

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
            className="bg-white rounded-lg shadow-md max-w-2xl w-full max-h-[90vh] overflow-y-auto"
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
            className="bg-white rounded-lg shadow-md max-w-3xl w-full max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-6">
              <ZoneIngestionWizard
                siteId={state.siteId}
                onComplete={() => {
                  dispatch({ type: "SET_ZONE_INGESTION_WIZARD", show: false });
                  dispatch({ type: "SET_STEP", step: 5 });
                }}
                onSkip={() => {
                  // User chose to skip zone configuration for now
                  dispatch({ type: "SET_ZONE_INGESTION_WIZARD", show: false });
                  dispatch({ type: "SET_STEP", step: 5 });
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
      {(state.step < 4 || state.step === 5) && (
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
