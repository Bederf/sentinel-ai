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
  Leaf,
  Sun,
  Droplets,
  Lightbulb,
} from "lucide-react";
import type { ModuleType } from "./moduleRegistry";

export type View =
  | "dashboard"
  | "ai-chat"
  | "digital-twin"
  | "aegis"
  | "technician"
  | "control"
  | "control-audit"
  | "optimization"
  | "settings"
  | "integrations"
  | "occupancy"
  | "occupancy-analytics"
  | "occupancy-energy-correlation"
  | "lighting"
  | "workflow"
  | "security"
  | "simbiot"
  | "simulation"
  | "sustainability"
  | "solar"
  | "solar-config"
  | "water"
  | "fleet"
  | "mlops"
  | "contracts"
  | "profitability"
  | "budget-report"
  | "modules"
  | "audit-logs";

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
  "ai-chat": "AI Chat",
  "digital-twin": "Digital Twin",
  aegis: "AEGIS Ops",
  technician: "Technician Chat",
  control: "Control Dashboard",
  "control-audit": "Control Audit Trail",
  "audit-logs": "Audit Logs",
  optimization: "Loadshedding",
  settings: "Settings",
  integrations: "System Health",
  occupancy: "Occupancy",
  "occupancy-analytics": "Occupancy Analytics",
  "occupancy-energy-correlation": "Energy Correlation",
  lighting: "Lighting",
  workflow: "Asset Workflow",
  security: "Security",
  simbiot: "SIMBIOT",
  simulation: "Simulation",
  sustainability: "Sustainability & ESG",
  solar: "Solar & BESS",
  "solar-config": "Solar Setup Wizard",
  water: "Water Consumption",
  fleet: "Fleet ML Insights",
  mlops: "ML Metrics",
  contracts: "Contract Management",
  profitability: "Profitability Dashboard",
  "budget-report": "Budget Reports",
  modules: "Module Manager",
};

/**
 * Base sidebar items — always visible.
 * Dashboard, AI Chat, SIMBIOT (moved from addon), Settings (moved from internal).
 * Settings requires admin or demo user (checked in Sidebar component).
 */
export const BASE_NAV_ITEMS: NavItem[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard, description: "Overview and AI recommendations", category: "base" },
  { id: "ai-chat", label: "AI Chat", icon: MessageSquare, description: "SENTINEL AI Assistant", category: "base" },
  { id: "simbiot", label: "SIMBIOT", icon: Plug, description: "BMS Connection Wizard", category: "base" },
  { id: "settings", label: "Settings", icon: SettingsIcon, description: "Admin settings", category: "base", requiredRole: "admin" },
];

/**
 * Addon items — EMPTY. All moved to building detail tabs.
 * Kept for backward compatibility with ViewGuard and access-control.
 */
export const ADDON_NAV_ITEMS: NavItem[] = [];

/**
 * Internal items — EMPTY. Settings moved to base.
 * Kept for backward compatibility with ViewGuard and access-control.
 */
export const INTERNAL_NAV_ITEMS: NavItem[] = [];

/** All nav items combined (for lookup) */
export const ALL_NAV_ITEMS: NavItem[] = [
  ...BASE_NAV_ITEMS,
  ...ADDON_NAV_ITEMS,
  ...INTERNAL_NAV_ITEMS,
];

// ─── Building Detail Tabs (Consolidated: 7 tabs) ────────────────────

export type BuildingTabId =
  | "overview"
  | "system-health"
  | "operations"
  | "lighting-occupancy"
  | "solar-bess"
  | "energy"
  | "water";

export interface BuildingTabItem {
  id: BuildingTabId;
  label: string;
  icon: LucideIcon;
}

/**
 * Building detail tab definitions — 7 consolidated tabs.
 * Rendered as a single-row tab bar inside SiteDetail (no scrolling needed).
 * Merged tabs use internal sub-tab pills for their child views.
 */
export const BUILDING_TAB_ITEMS: BuildingTabItem[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "system-health", label: "System Health", icon: Activity },
  { id: "operations", label: "Operations", icon: Shield },
  { id: "lighting-occupancy", label: "Lighting & Occupancy", icon: Lightbulb },
  { id: "solar-bess", label: "Solar & BESS", icon: Sun },
  { id: "energy", label: "Energy", icon: Leaf },
  { id: "water", label: "Water", icon: Droplets },
];

// ─── Legacy helpers (kept for ViewGuard / access-control compatibility) ──

/** localStorage key for persisted addon ordering (no longer used, kept for cleanup) */
export const SIDEBAR_ORDER_KEY = "sentinel_sidebar_order";

/**
 * Check if a view requires an active module to be accessible.
 * Consolidated tabs no longer have module gates — all 7 are always visible.
 */
export function isModuleGatedView(_view: View): boolean {
  return false;
}

/**
 * Get the required module for a gated view, if any.
 * Consolidated tabs have no module gates.
 */
export function getRequiredModule(_view: View): ModuleType | undefined {
  return undefined;
}
