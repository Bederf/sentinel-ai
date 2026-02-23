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
  TrendingUp,
  TrendingDown,
  Droplets,
  DollarSign,
  Brain,
  Box,
  Lightbulb,
  History,
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

// ─── Building Detail Tabs ────────────────────────────────────────────

export type BuildingTabId =
  | "overview"
  | "system-health"
  | "control"
  | "digital-twin"
  | "audit-logs"
  | "tech-chat"
  | "loadshedding"
  | "lighting"
  | "occupancy"
  | "occupancy-analytics"
  | "energy-correlation"
  | "solar"
  | "aegis"
  | "security"
  | "water"
  | "esg"
  | "asset-workflow"
  | "contracts"
  | "profitability"
  | "budget"
  | "fleet-ml"
  | "ml-metrics"
  | "simulation";

export interface BuildingTabItem {
  id: BuildingTabId;
  label: string;
  icon: LucideIcon;
  requiredModule?: ModuleType;
  requiredRole?: "admin";
}

/**
 * Building detail tab definitions.
 * Rendered as a scrollable tab bar inside SiteDetail.
 * Module-gated: tabs only appear when the required module is active.
 */
export const BUILDING_TAB_ITEMS: BuildingTabItem[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "system-health", label: "System Health", icon: Activity },
  { id: "control", label: "Control", icon: Shield, requiredModule: "control" },
  { id: "digital-twin", label: "Digital Twin", icon: Box },
  { id: "audit-logs", label: "Audit Logs", icon: History },
  { id: "tech-chat", label: "Tech Chat", icon: Wrench, requiredModule: "maintenance" },
  { id: "loadshedding", label: "Loadshedding", icon: Zap, requiredModule: "energy" },
  { id: "lighting", label: "Lighting", icon: Lightbulb, requiredModule: "lighting" },
  { id: "occupancy", label: "Occupancy", icon: Users, requiredModule: "lighting" },
  { id: "occupancy-analytics", label: "Occ. Analytics", icon: BarChart3, requiredModule: "lighting" },
  { id: "energy-correlation", label: "Energy Correlation", icon: TrendingDown, requiredModule: "lighting" },
  { id: "solar", label: "Solar & BESS", icon: Sun, requiredModule: "solar" },
  { id: "aegis", label: "AEGIS", icon: Brain, requiredModule: "solar" },
  { id: "security", label: "Security", icon: ShieldCheck, requiredModule: "security" },
  { id: "water", label: "Water", icon: Droplets, requiredModule: "water" },
  { id: "esg", label: "ESG", icon: Leaf, requiredModule: "sustainability" },
  { id: "asset-workflow", label: "Asset Workflow", icon: GitBranch, requiredModule: "assets" },
  { id: "contracts", label: "Contracts", icon: FileText, requiredModule: "contracts" },
  { id: "profitability", label: "Profitability", icon: TrendingUp, requiredModule: "contracts" },
  { id: "budget", label: "Budget", icon: DollarSign, requiredModule: "contracts" },
  { id: "fleet-ml", label: "Fleet ML", icon: BarChart3, requiredModule: "ml" },
  { id: "ml-metrics", label: "ML Metrics", icon: Brain, requiredModule: "ml" },
  { id: "simulation", label: "Simulation", icon: FlaskConical, requiredModule: "ml", requiredRole: "admin" },
];

// ─── Legacy helpers (kept for ViewGuard / access-control compatibility) ──

/** localStorage key for persisted addon ordering (no longer used, kept for cleanup) */
export const SIDEBAR_ORDER_KEY = "sentinel_sidebar_order";

/**
 * Check if a view requires an active module to be accessible.
 */
export function isModuleGatedView(view: View): boolean {
  // Check both old addon items (empty) and building tabs
  const tabItem = BUILDING_TAB_ITEMS.find((t) => t.id === view || mapTabToView(t.id) === view);
  return !!tabItem?.requiredModule;
}

/**
 * Get the required module for a gated view, if any.
 */
export function getRequiredModule(view: View): ModuleType | undefined {
  const tabItem = BUILDING_TAB_ITEMS.find((t) => t.id === view || mapTabToView(t.id) === view);
  return tabItem?.requiredModule;
}

/** Map a BuildingTabId to the legacy View id where they differ */
function mapTabToView(tabId: BuildingTabId): View | undefined {
  const map: Partial<Record<BuildingTabId, View>> = {
    "system-health": "integrations",
    "tech-chat": "technician",
    "loadshedding": "optimization",
    "occupancy-analytics": "occupancy-analytics",
    "energy-correlation": "occupancy-energy-correlation",
    "aegis": "aegis",
    "esg": "sustainability",
    "asset-workflow": "workflow",
    "budget": "budget-report",
    "fleet-ml": "fleet",
    "ml-metrics": "mlops",
  };
  return map[tabId];
}
