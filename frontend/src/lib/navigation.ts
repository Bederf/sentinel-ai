/**
 * Navigation Configuration - Module-Gated Sidebar
 *
 * Defines all navigation items with module gating metadata.
 * Items are categorised as:
 * - base: always visible to all users
 * - addon: visible only when the required module is active (paid add-ons)
 * - internal: visible only to users with the required role
 */

import type { LucideIcon } from "lucide-react";
import {
  MessageSquare,
  LayoutDashboard,
  Shield,
  ClipboardList,
  Settings as SettingsIcon,
  Zap,
  Wrench,
  Activity,
  Users,
  GitBranch,
  ShieldCheck,
  Plug,
  FlaskConical,
  BarChart3,
  Leaf,
  Sun,
  FileText,
} from "lucide-react";
import type { ModuleType } from "./moduleRegistry";

export type View =
  | "dashboard"
  | "chat"
  | "technician"
  | "control"
  | "control-audit"
  | "optimization"
  | "settings"
  | "integrations"
  | "occupancy"
  | "workflow"
  | "security"
  | "simbiot"
  | "simulation"
  | "sustainability"
  | "solar"
  | "fleet"
  | "mlops"
  | "contracts";

export type NavCategory = "base" | "addon" | "internal";

export interface NavItem {
  id: View;
  label: string;
  icon: LucideIcon;
  description?: string;
  category: NavCategory;
  requiredModule?: ModuleType;
  requiredRole?: "admin";
  defaultOrder?: number;
}

/** View title mapping used by the header */
export const VIEW_TITLES: Record<View, string> = {
  dashboard: "Dashboard",
  chat: "AI Assistant",
  technician: "Technician Chat",
  control: "Control Dashboard",
  "control-audit": "Control Audit Trail",
  optimization: "Load Shedding Optimization",
  settings: "Settings",
  integrations: "Integration Monitoring",
  occupancy: "DALI Occupancy",
  workflow: "Asset Workflow",
  security: "Security",
  simbiot: "SIMBIOT",
  simulation: "Simulation",
  sustainability: "Sustainability & ESG",
  solar: "Solar & BESS",
  fleet: "Fleet ML Insights",
  mlops: "ML Metrics",
  contracts: "Contract Management",
};

/**
 * Base navigation items - always visible to all authenticated users.
 */
export const BASE_NAV_ITEMS: NavItem[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard, description: "System overview", category: "base" },
  { id: "chat", label: "Chat", icon: MessageSquare, description: "AI Assistant", category: "base" },
  { id: "control", label: "Control", icon: Shield, description: "Building Controls", category: "base" },
  { id: "control-audit", label: "Control Audit", icon: ClipboardList, description: "Control System Logs", category: "base" },
  { id: "workflow", label: "Asset Workflow", icon: GitBranch, description: "Lifecycle Management", category: "base" },
  { id: "simbiot", label: "SIMBIOT", icon: Plug, description: "BMS Connection Wizard", category: "base" },
  { id: "contracts", label: "Contracts", icon: FileText, description: "Contract & SLA Management", category: "base" },
  { id: "integrations", label: "Integrations", icon: Activity, description: "BMS Integration Health", category: "base" },
  { id: "settings", label: "Settings", icon: SettingsIcon, description: "System Configuration", category: "base" },
];

/**
 * Add-on navigation items - visible only when the required module is active.
 * These represent paid bolt-on modules.
 */
export const ADDON_NAV_ITEMS: NavItem[] = [
  { id: "technician", label: "Tech Chat", icon: Wrench, description: "Fault Diagnosis", category: "addon", requiredModule: "hvac", defaultOrder: 0 },
  { id: "optimization", label: "Optimization", icon: Zap, description: "Load Shedding AI", category: "addon", requiredModule: "energy", defaultOrder: 1 },
  { id: "occupancy", label: "Occupancy", icon: Users, description: "DALI Lighting", category: "addon", requiredModule: "lighting", defaultOrder: 2 },
  { id: "security", label: "Security", icon: ShieldCheck, description: "Access & CCTV", category: "addon", requiredModule: "security", defaultOrder: 3 },
  { id: "solar", label: "Solar & BESS", icon: Sun, description: "PV & Battery Storage", category: "addon", requiredModule: "solar", defaultOrder: 4 },
  { id: "sustainability", label: "ESG", icon: Leaf, description: "Sustainability & Carbon", category: "addon", requiredModule: "sustainability", defaultOrder: 5 },
  { id: "fleet", label: "Fleet ML", icon: BarChart3, description: "Cross-Site Insights", category: "addon", requiredModule: "ml", defaultOrder: 6 },
  { id: "mlops", label: "ML Metrics", icon: Activity, description: "MLOps Monitoring", category: "addon", requiredModule: "ml", defaultOrder: 7 },
];

/**
 * Internal navigation items - visible only to users with matching role.
 */
export const INTERNAL_NAV_ITEMS: NavItem[] = [
  { id: "simulation", label: "Simulation", icon: FlaskConical, description: "Lifecycle & Analytics", category: "internal", requiredRole: "admin" },
];

/** All nav items combined (for lookup) */
export const ALL_NAV_ITEMS: NavItem[] = [
  ...BASE_NAV_ITEMS,
  ...ADDON_NAV_ITEMS,
  ...INTERNAL_NAV_ITEMS,
];

/** localStorage key for persisted addon ordering */
export const SIDEBAR_ORDER_KEY = "sentinel_sidebar_order";

/**
 * Get the persisted addon order from localStorage.
 * Returns an array of View ids representing the user's preferred order.
 */
export function getPersistedAddonOrder(): View[] {
  try {
    const stored = localStorage.getItem(SIDEBAR_ORDER_KEY);
    if (stored) {
      return JSON.parse(stored) as View[];
    }
  } catch {
    // ignore parse errors
  }
  return [];
}

/**
 * Persist addon order to localStorage.
 */
export function persistAddonOrder(order: View[]): void {
  localStorage.setItem(SIDEBAR_ORDER_KEY, JSON.stringify(order));
}

/**
 * Check if a view requires an active module to be accessible.
 */
export function isModuleGatedView(view: View): boolean {
  return ADDON_NAV_ITEMS.some((item) => item.id === view);
}

/**
 * Get the required module for a gated view, if any.
 */
export function getRequiredModule(view: View): ModuleType | undefined {
  const item = ADDON_NAV_ITEMS.find((i) => i.id === view);
  return item?.requiredModule;
}
