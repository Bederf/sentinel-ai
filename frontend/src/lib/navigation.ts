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
  TrendingUp,
  TrendingDown,
  Droplets,
  DollarSign,
  Brain,
  Box,
  Lightbulb,
} from "lucide-react";
import type { ModuleType } from "./moduleRegistry";

export type View =
  | "dashboard"
  | "ai-chat"
  | "digital-twin"
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
  | "modules";

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
  technician: "Technician Chat",
  control: "Control Dashboard",
  "control-audit": "Control Audit Trail",
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
 * Base navigation items - always visible, cannot be disabled.
 * FREE BASIC PACKAGE PAGES:
 * - Dashboard: view equipment and AI recommendations
 * - System Health: real-time building monitoring
 * - AI Chat: SENTINEL AI assistant
 * - Digital Twin: 3D/2D building visualization
 */
export const BASE_NAV_ITEMS: NavItem[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard, description: "Overview and AI recommendation", category: "base" },
  { id: "integrations", label: "System Health", icon: Activity, description: "Real-time Health Monitoring", category: "base" },
  { id: "ai-chat", label: "AI Chat", icon: MessageSquare, description: "SENTINEL AI Assistant", category: "base" },
  { id: "digital-twin", label: "Digital Twin", icon: Box, description: "3D/2D Building Visualization", category: "base" },
];

/**
 * Module-gated navigation items - visible only when the required module is active.
 * All modules ship with every deployment; clients activate/deactivate per site.
 *
 * Core modules (control, assets, simbiot, integrations) are typically always active
 * but CAN be disabled if a client doesn't need them.
 */
export const ADDON_NAV_ITEMS: NavItem[] = [
  // Core operations modules
  { id: "control", label: "Control", icon: Shield, description: "Building Controls", category: "addon", requiredModule: "control", defaultOrder: 0 },
  { id: "workflow", label: "Asset Workflow", icon: GitBranch, description: "Lifecycle Management", category: "addon", requiredModule: "assets", defaultOrder: 2 },
  { id: "simbiot", label: "SIMBIOT", icon: Plug, description: "BMS Connection Wizard", category: "addon", requiredModule: "simbiot", defaultOrder: 3 },
  // Building system modules
  { id: "technician", label: "Tech Chat", icon: Wrench, description: "Fault Diagnosis", category: "addon", requiredModule: "assets", defaultOrder: 10 },
  { id: "optimization", label: "Loadshedding", icon: Zap, description: "Load Shedding AI", category: "addon", requiredModule: "energy", defaultOrder: 11 },
  { id: "occupancy", label: "Occupancy", icon: Users, description: "Occupancy Monitoring", category: "addon", requiredModule: "lighting", defaultOrder: 12 },
  { id: "occupancy-analytics", label: "Occupancy Analytics", icon: BarChart3, description: "Occupancy Trends & Insights", category: "addon", requiredModule: "lighting", defaultOrder: 12.2 },
  { id: "occupancy-energy-correlation", label: "Energy Correlation", icon: TrendingDown, description: "Occupancy vs Energy Savings", category: "addon", requiredModule: "lighting", defaultOrder: 12.3 },
  { id: "lighting", label: "Lighting", icon: Lightbulb, description: "Lighting Control", category: "addon", requiredModule: "lighting", defaultOrder: 12.5 },
  { id: "security", label: "Security", icon: ShieldCheck, description: "Access & CCTV", category: "addon", requiredModule: "security", defaultOrder: 13 },
  { id: "solar", label: "Solar & BESS", icon: Sun, description: "PV & Battery Storage", category: "addon", requiredModule: "solar", defaultOrder: 14 },
  { id: "water", label: "Water", icon: Droplets, description: "Water Consumption", category: "addon", requiredModule: "water", defaultOrder: 15 },
  { id: "sustainability", label: "ESG", icon: Leaf, description: "Sustainability & Carbon", category: "addon", requiredModule: "sustainability", defaultOrder: 16 },
  { id: "contracts", label: "Contracts", icon: FileText, description: "Contract & SLA", category: "addon", requiredModule: "contracts", defaultOrder: 17 },
  { id: "profitability", label: "Profitability", icon: TrendingUp, description: "Profitability Analytics", category: "addon", requiredModule: "contracts", defaultOrder: 18 },
  { id: "budget-report", label: "Budget Reports", icon: DollarSign, description: "Budget Reporting", category: "addon", requiredModule: "contracts", defaultOrder: 19 },
  // Intelligence modules
  { id: "fleet", label: "Fleet ML", icon: BarChart3, description: "Cross-Site Insights", category: "addon", requiredModule: "ml", defaultOrder: 20 },
  { id: "mlops", label: "ML Metrics", icon: Brain, description: "MLOps Monitoring", category: "addon", requiredModule: "ml", defaultOrder: 21 },
];

/**
 * Internal navigation items - visible only to users with matching role.
 * Settings is password-protected and visible to both admin and demo users.
 */
export const INTERNAL_NAV_ITEMS: NavItem[] = [
  { id: "simulation", label: "Simulation", icon: FlaskConical, description: "Lifecycle & Analytics", category: "internal", requiredRole: "admin", requiredModule: "ml" },
  { id: "settings", label: "Settings", icon: SettingsIcon, description: "Admin settings", category: "internal", requiredRole: "admin" },
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
