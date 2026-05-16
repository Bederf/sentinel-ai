/**
 * Navigation Configuration - Sidebar + Building Detail Tabs
 *
 * Sidebar items: Dashboard, AI Chat, SIMBIOT, Settings (+ About/Info)
 * Building tabs: All site-specific views, module-gated, shown inside SiteDetail
 */

import type { LucideIcon } from "lucide-react";
import {
  MessageSquare,
  LayoutDashboard,
  Shield,
  Settings as SettingsIcon,
  Activity,
  Plug,
  FileText,
  Wrench,
  DollarSign,
  Brain,
  Sun,
  Droplets,
  Lightbulb,
  Sliders,
  LayoutGrid,
  Fuel,
  Leaf,
  ClipboardCheck,
} from "lucide-react";
import type { ModuleType } from "./moduleRegistry";

export type View =
  | "dashboard"
  | "ai-chat"
  | "integrations"
  | "logs"
  | "maintenance"
  | "simbiot"
  | "settings"
  | "financial"
  | "fleet-ml"
  | "compliance"
  | "digital-twin"
  | "optimization";

export type NavCategory = "base" | "addon" | "admin";

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
  "ai-chat": "AI Chat",
  integrations: "System Health",
  logs: "Logs",
  maintenance: "Maintenance",
  simbiot: "SIMBIOT",
  settings: "Settings",
  financial: "Financial",
  "fleet-ml": "Fleet ML",
  compliance: "Compliance",
  "digital-twin": "Digital Twin",
  optimization: "AI Optimization",
};

/**
 * Base sidebar items — always visible (4 items).
 */
export const BASE_NAV_ITEMS: NavItem[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard, description: "Overview and AI recommendations", category: "base" },
  { id: "ai-chat", label: "AI Chat", icon: MessageSquare, description: "SENTINEL AI Assistant", category: "base" },
  { id: "integrations", label: "System Health", icon: Activity, description: "Integration monitoring", category: "base" },
  { id: "logs", label: "Logs", icon: FileText, description: "Audit trail and event logs", category: "base" },
  { id: "maintenance", label: "Maintenance", icon: Wrench, description: "Equipment, work orders & tech chat", category: "base", requiredModule: "maintenance" },
];

/**
 * Admin-only sidebar items (2 items).
 */
export const ADMIN_NAV_ITEMS: NavItem[] = [
  { id: "simbiot", label: "SIMBIOT", icon: Plug, description: "Site ingestion, discovery, and intake controls", category: "admin", requiredRole: "admin" },
  { id: "settings", label: "Settings", icon: SettingsIcon, description: "Admin settings", category: "admin", requiredRole: "admin" },
];

/**
 * Conditional add-on sidebar items (4 items).
 * Only visible when the respective add-on module is active.
 */
export const ADDON_NAV_ITEMS: NavItem[] = [
  { id: "digital-twin", label: "Digital Twin", icon: Activity, description: "3D building visualization", category: "addon", requiredModule: "digital_twin" },
  { id: "optimization", label: "AI Optimization", icon: TrendingUp, description: "Recommendations setpoint adjustments", category: "addon", requiredModule: "optimization" },
  { id: "financial",   label: "Financial",   icon: DollarSign,      description: "Contracts and billing",            category: "addon", requiredModule: "financial" },
  { id: "fleet-ml",   label: "Fleet ML",    icon: Brain,           description: "Cross-site analytics",             category: "addon", requiredModule: "fleet_ml" },
  { id: "compliance", label: "Compliance",  icon: ClipboardCheck,  description: "OHS, Fire, Electrical, Lift safety", category: "addon", requiredModule: "compliance" },
];

/** All nav items combined (for lookup) */
export const ALL_NAV_ITEMS: NavItem[] = [
  ...BASE_NAV_ITEMS,
  ...ADMIN_NAV_ITEMS,
  ...ADDON_NAV_ITEMS,
];

// ─── Building Detail Tabs (10 tabs, connected-site-data-driven) ─────────────

export type BuildingTabId =
  | "overview"
  | "hvac"
  | "energy"
  | "lighting"
  | "solar-bess"
  | "water"
  | "fire"
  | "security"
  | "digital-twin"
  | "controls"
  | "space"
  | "fuel"
  | "esg";

export interface BuildingTabItem {
  id: BuildingTabId;
  label: string;
  icon: LucideIcon;
  /** Module that gates the control features within this tab (not tab visibility) */
  controlModule?: ModuleType;
  /** If set, tab only shows when this site has the matching module active */
  requiredModule?: ModuleType;
}

/**
 * Building detail tab definitions.
 * Tabs should only appear when the selected site has the matching module active.
 * Control features within each tab are gated separately by the respective {x}_control add-on.
 * Fire tab has no control toggle (always read-only when present).
 */
export const BUILDING_TAB_ITEMS: BuildingTabItem[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "hvac", label: "HVAC", icon: Activity, controlModule: "hvac_control", requiredModule: "hvac" },
  { id: "energy", label: "Energy", icon: Activity, controlModule: "energy_control", requiredModule: "energy" },
  { id: "lighting", label: "Lighting", icon: Lightbulb, controlModule: "lighting_control", requiredModule: "lighting" },
  { id: "solar-bess", label: "Solar & BESS", icon: Sun, controlModule: "solar_control", requiredModule: "solar" },
  { id: "water", label: "Water", icon: Droplets, controlModule: "water_control", requiredModule: "water" },
  { id: "fire", label: "Fire", icon: Activity, requiredModule: "fire" },
  { id: "security", label: "Security", icon: Shield, controlModule: "security_control", requiredModule: "security" },
  { id: "controls", label: "Controls", icon: Sliders },
  { id: "space", label: "Space", icon: LayoutGrid, requiredModule: "space_optimization" },
  { id: "fuel", label: "Fuel", icon: Fuel, requiredModule: "fuel" },
  { id: "esg", label: "ESG", icon: Leaf, requiredModule: "compliance" },
];

// ─── Helpers ──

/** localStorage key for persisted addon ordering */
export const SIDEBAR_ORDER_KEY = "sentinel_sidebar_order";

/**
 * Check if a view requires an active module to be accessible.
 * Only add-on sidebar items have module gates.
 */
export function isModuleGatedView(view: View): boolean {
  const item = ADDON_NAV_ITEMS.find(i => i.id === view);
  return !!item?.requiredModule;
}

/**
 * Get the required module for a gated view, if any.
 */
export function getRequiredModule(view: View): ModuleType | undefined {
  const item = ADDON_NAV_ITEMS.find(i => i.id === view);
  return item?.requiredModule;
}
