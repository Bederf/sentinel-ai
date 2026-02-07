/**
 * Sidebar Navigation Component - SENTINEL Branding
 *
 * Module-gated sidebar with three sections:
 * - Base: always visible (Dashboard, Chat, Control, etc.)
 * - Modules: visible when required module is active (paid add-ons)
 * - Internal: visible to admin users only (Simulation)
 *
 * Add-on items can be reordered with up/down arrows (persisted in localStorage).
 */

import { useState, useMemo, useCallback } from "react";
import {
  Menu,
  X,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  ChevronUp,
  Info,
  SlidersHorizontal,
} from "lucide-react";
import { useModules } from "../contexts/ModuleContext";
import {
  type View,
  type NavItem,
  BASE_NAV_ITEMS,
  ADDON_NAV_ITEMS,
  INTERNAL_NAV_ITEMS,
  getPersistedAddonOrder,
  persistAddonOrder,
} from "../lib/navigation";

export type { View } from "../lib/navigation";

interface SidebarProps {
  currentView: View;
  onViewChange: (view: View) => void;
  version?: string;
  onCustomizeDashboard?: () => void;
  userRole?: string;
}

export function Sidebar({ currentView, onViewChange, version = "13.0", onCustomizeDashboard, userRole }: SidebarProps) {
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [isAboutOpen, setIsAboutOpen] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(true); // Start minimized
  const [addonOrder, setAddonOrder] = useState<View[]>(() => getPersistedAddonOrder());

  const { isModuleActive, activeModules } = useModules();

  // Compute visible addon items, filtered by active modules and sorted by user order
  const visibleAddons = useMemo(() => {
    const active = ADDON_NAV_ITEMS.filter(
      (item) => item.requiredModule && isModuleActive(item.requiredModule)
    );

    // Sort by persisted order, falling back to defaultOrder
    if (addonOrder.length > 0) {
      return [...active].sort((a, b) => {
        const aIdx = addonOrder.indexOf(a.id);
        const bIdx = addonOrder.indexOf(b.id);
        const aOrder = aIdx >= 0 ? aIdx : (a.defaultOrder ?? 999);
        const bOrder = bIdx >= 0 ? bIdx : (b.defaultOrder ?? 999);
        return aOrder - bOrder;
      });
    }

    return [...active].sort((a, b) => (a.defaultOrder ?? 0) - (b.defaultOrder ?? 0));
  }, [isModuleActive, addonOrder]);

  // Compute visible internal items, filtered by role
  const visibleInternal = useMemo(() => {
    return INTERNAL_NAV_ITEMS.filter(
      (item) => !item.requiredRole || userRole === item.requiredRole
    );
  }, [userRole]);

  const handleNavClick = (view: View) => {
    onViewChange(view);
    setIsMobileOpen(false);
  };

  // Reorder addon items
  const moveAddon = useCallback((itemId: View, direction: "up" | "down") => {
    setAddonOrder((prev) => {
      // Build current order from visible addons
      const currentIds = visibleAddons.map((i) => i.id);
      const ordered = prev.length > 0
        ? [...currentIds].sort((a, b) => {
            const aIdx = prev.indexOf(a);
            const bIdx = prev.indexOf(b);
            return (aIdx >= 0 ? aIdx : 999) - (bIdx >= 0 ? bIdx : 999);
          })
        : currentIds;

      const idx = ordered.indexOf(itemId);
      if (idx < 0) return prev;

      const swapIdx = direction === "up" ? idx - 1 : idx + 1;
      if (swapIdx < 0 || swapIdx >= ordered.length) return prev;

      const newOrder = [...ordered];
      [newOrder[idx], newOrder[swapIdx]] = [newOrder[swapIdx], newOrder[idx]];

      persistAddonOrder(newOrder);
      return newOrder;
    });
  }, [visibleAddons]);

  const renderNavItem = (item: NavItem, isActive: boolean, showReorder?: { index: number; total: number }) => {
    const Icon = item.icon;

    return (
      <div key={item.id} className="relative group">
        <button
          onClick={() => handleNavClick(item.id)}
          className={`
            w-full flex items-center gap-3 px-4 py-2.5 mb-1 mx-auto
            transition-all duration-150 ease-in-out
            md:justify-center lg:justify-start
            hover:brightness-110
            ${!isActive ? 'hover:bg-white/5' : ''}
          `}
          style={{
            background: isActive ? "rgba(255, 255, 255, 0.08)" : "transparent",
            borderLeft: isActive ? "3px solid var(--color-sentinel-amber)" : "3px solid transparent",
            color: isActive ? "var(--color-sentinel-text-primary)" : "var(--color-sentinel-text-secondary)",
          }}
          aria-current={isActive ? "page" : undefined}
        >
          <Icon
            className="h-5 w-5 flex-shrink-0"
            style={{
              color: isActive ? "var(--color-sentinel-amber)" : "var(--color-sentinel-text-secondary)",
            }}
          />
          <div className={`flex flex-col items-start flex-1 md:hidden ${isCollapsed ? 'lg:hidden' : 'lg:flex'}`}>
            <span className="font-medium text-sm">{item.label}</span>
            {item.description && (
              <span
                className="text-xs"
                style={{ color: "var(--color-grafana-text-disabled)" }}
              >
                {item.description}
              </span>
            )}
          </div>
        </button>

        {/* Reorder arrows for addon items (expanded sidebar only) */}
        {showReorder && !isCollapsed && (
          <div className={`absolute right-2 top-1/2 -translate-y-1/2 hidden lg:flex flex-col gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity`}>
            {showReorder.index > 0 && (
              <button
                onClick={(e) => { e.stopPropagation(); moveAddon(item.id, "up"); }}
                className="p-0.5 rounded hover:bg-[var(--color-sentinel-bg-panel)] transition-colors"
                aria-label={`Move ${item.label} up`}
              >
                <ChevronUp className="h-3 w-3" style={{ color: "var(--color-sentinel-text-secondary)" }} />
              </button>
            )}
            {showReorder.index < showReorder.total - 1 && (
              <button
                onClick={(e) => { e.stopPropagation(); moveAddon(item.id, "down"); }}
                className="p-0.5 rounded hover:bg-[var(--color-sentinel-bg-panel)] transition-colors"
                aria-label={`Move ${item.label} down`}
              >
                <ChevronDown className="h-3 w-3" style={{ color: "var(--color-sentinel-text-secondary)" }} />
              </button>
            )}
          </div>
        )}
      </div>
    );
  };

  // Module emoji mapping for About section
  const moduleEmojis: Record<string, string> = {
    control: "\uD83D\uDEE1\uFE0F", // shield
    assets: "\uD83D\uDD27", // wrench
    simbiot: "\uD83D\uDD0C", // plug
    integrations: "\uD83D\uDCE1", // satellite
    notifications: "\uD83D\uDD14", // bell
    contracts: "\uD83D\uDCC4", // document
    hvac: "\u2744", // snowflake
    energy: "\u26A1",
    security: "\uD83D\uDD12",
    lighting: "\uD83D\uDCA1",
    fire: "\uD83D\uDD25",
    access: "\uD83D\uDD11",
    solar: "\u2600\uFE0F",
    ml: "\uD83E\uDDE0",
    sustainability: "\uD83C\uDF3F",
  };

  return (
    <>
      {/* Mobile hamburger button */}
      <button
        onClick={() => setIsMobileOpen(!isMobileOpen)}
        className="md:hidden fixed top-4 left-4 z-50 p-2 rounded-md transition-colors hover:brightness-125 glass-subtle"
        aria-label={isMobileOpen ? "Close menu" : "Open menu"}
      >
        {isMobileOpen ? (
          <X className="h-5 w-5" style={{ color: "var(--color-grafana-text-primary)" }} />
        ) : (
          <Menu className="h-5 w-5" style={{ color: "var(--color-grafana-text-primary)" }} />
        )}
      </button>

      {/* Mobile overlay */}
      {isMobileOpen && (
        <div
          className="md:hidden fixed inset-0 z-30"
          style={{ background: "rgba(0, 0, 0, 0.6)" }}
          onClick={() => setIsMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed md:relative inset-y-0 left-0 z-40
          w-64 md:w-16 ${isCollapsed ? 'lg:w-16' : 'lg:w-56'}
          transform transition-all duration-200 ease-in-out
          ${isMobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}
          flex flex-col
        `}
        style={{
          background: "var(--glass-bg)",
          backdropFilter: "blur(var(--glass-blur-lg)) saturate(180%)",
          WebkitBackdropFilter: "blur(var(--glass-blur-lg)) saturate(180%)",
          borderRight: "1px solid var(--glass-border)",
        }}
      >
        {/* Sidebar Header */}
        <div
          className="flex-none h-16 flex items-center justify-center px-4 mt-14 md:mt-0 relative"
          style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
        >
          <div className={`flex items-center gap-3 w-full justify-center md:justify-center ${isCollapsed ? 'lg:hidden' : 'lg:flex lg:justify-start'}`}>
            <div className={`md:hidden ${isCollapsed ? 'lg:hidden' : 'lg:block'}`}>
              <span
                className="font-semibold text-sm tracking-wide"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                SENTINEL
              </span>
              <div
                className="text-[10px] tracking-wider"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                ASSET PROTECTION
              </div>
            </div>
          </div>
          {/* Toggle button */}
          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className={`hidden lg:flex absolute top-1/2 transform -translate-y-1/2 p-1 rounded hover:brightness-125 hover:scale-110 transition-all duration-200 ${
              isCollapsed
                ? 'left-1/2 -translate-x-1/2'
                : 'right-2'
            }`}
            style={{
              background: "rgba(255, 255, 255, 0.08)",
              border: "1px solid var(--glass-border)",
            }}
            aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {isCollapsed ? (
              <ChevronRight className="h-4 w-4" style={{ color: "var(--color-sentinel-text-secondary)" }} />
            ) : (
              <ChevronLeft className="h-4 w-4" style={{ color: "var(--color-sentinel-text-secondary)" }} />
            )}
          </button>
        </div>

        {/* Navigation items */}
        <nav className="flex-1 py-4 overflow-y-auto" role="navigation">
          {/* Base section */}
          <div className="px-3 mb-2">
            <span
              className={`text-xs font-medium uppercase tracking-wider md:hidden ${isCollapsed ? 'lg:hidden' : 'lg:block'}`}
              style={{ color: "var(--color-grafana-text-disabled)" }}
            >
              Menu
            </span>
          </div>

          {BASE_NAV_ITEMS.map((item) =>
            renderNavItem(item, currentView === item.id)
          )}

          {/* Addon section - only shown if there are active add-on modules */}
          {visibleAddons.length > 0 && (
            <>
              <div
                className="mx-3 mt-3 mb-2 pt-3"
                style={{ borderTop: "1px solid var(--color-grafana-border)" }}
              >
                <span
                  className={`text-xs font-medium uppercase tracking-wider md:hidden ${isCollapsed ? 'lg:hidden' : 'lg:block'}`}
                  style={{ color: "var(--color-grafana-text-disabled)" }}
                >
                  Modules
                </span>
              </div>

              {visibleAddons.map((item, index) =>
                renderNavItem(item, currentView === item.id, {
                  index,
                  total: visibleAddons.length,
                })
              )}
            </>
          )}

          {/* Internal section - only shown if there are visible internal items */}
          {visibleInternal.length > 0 && (
            <>
              <div
                className="mx-3 mt-3 mb-2 pt-3"
                style={{ borderTop: "1px solid var(--color-grafana-border)" }}
              >
                <span
                  className={`text-xs font-medium uppercase tracking-wider md:hidden ${isCollapsed ? 'lg:hidden' : 'lg:block'}`}
                  style={{ color: "var(--color-grafana-text-disabled)" }}
                >
                  Internal
                </span>
              </div>

              {visibleInternal.map((item) =>
                renderNavItem(item, currentView === item.id)
              )}
            </>
          )}

          {/* Customize Dashboard Button */}
          {onCustomizeDashboard && (
            <div className="mt-4 mx-3">
              <button
                onClick={() => {
                  onCustomizeDashboard();
                  setIsMobileOpen(false);
                }}
                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-150 md:justify-center lg:justify-start hover:brightness-125 hover:scale-[1.02]"
                style={{
                  background: "rgba(245, 158, 11, 0.1)",
                  border: "1px solid rgba(245, 158, 11, 0.3)",
                  color: "var(--color-sentinel-amber)",
                }}
              >
                <SlidersHorizontal className="h-5 w-5 flex-shrink-0" />
                <div className={`flex flex-col items-start md:hidden ${isCollapsed ? 'lg:hidden' : 'lg:flex'}`}>
                  <span className="font-medium text-sm">Customize</span>
                  <span
                    className="text-xs"
                    style={{ color: "var(--color-grafana-text-disabled)" }}
                  >
                    Dashboard Cards
                  </span>
                </div>
              </button>
            </div>
          )}

          {/* About Section */}
          <div
            className="mt-4 pt-4 mx-3"
            style={{ borderTop: "1px solid var(--color-grafana-border)" }}
          >
            <button
              onClick={() => setIsAboutOpen(!isAboutOpen)}
              className={`w-full flex items-center gap-3 px-1 py-2 transition-all duration-150 md:justify-center hover:brightness-125 ${isCollapsed ? 'lg:justify-center' : 'lg:justify-start'}`}
              style={{
                color: isAboutOpen
                  ? "var(--color-sentinel-text-primary)"
                  : "var(--color-sentinel-text-secondary)",
              }}
            >
              <Info
                className="h-5 w-5 flex-shrink-0"
                style={{
                  color: isAboutOpen ? "var(--color-sentinel-amber)" : "var(--color-sentinel-text-secondary)",
                }}
              />
              <span className={`font-medium text-sm md:hidden ${isCollapsed ? 'lg:hidden' : 'lg:block'} flex-1 text-left`}>About</span>
              {isAboutOpen ? (
                <ChevronDown className={`h-4 w-4 md:hidden ${isCollapsed ? 'lg:hidden' : 'lg:block'}`} />
              ) : (
                <ChevronRight className={`h-4 w-4 md:hidden ${isCollapsed ? 'lg:hidden' : 'lg:block'}`} />
              )}
            </button>

            {/* Expandable about section */}
            {isAboutOpen && (
              <div className={`mt-2 md:hidden ${isCollapsed ? 'lg:hidden' : 'lg:block'}`}>
                <div
                  className="rounded p-3 text-xs space-y-3"
                  style={{
                    background: "var(--color-sentinel-bg-secondary)",
                    border: "1px solid var(--color-sentinel-border)",
                  }}
                >
                  <div>
                    <div
                      className="font-medium mb-1"
                      style={{ color: "var(--color-sentinel-amber)" }}
                    >
                      SENTINEL
                    </div>
                    <p style={{ color: "var(--color-sentinel-text-secondary)", lineHeight: "1.5" }}>
                      AI-powered facilities intelligence platform for proactive asset management.
                    </p>
                  </div>

                  <div>
                    <div
                      className="font-medium mb-1"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      Active Modules
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {activeModules.length > 0 ? (
                        activeModules
                          .filter((m) => m.status === "active")
                          .map((mod) => (
                            <span
                              key={mod.module_type}
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium"
                              style={{
                                background: "rgba(245, 158, 11, 0.15)",
                                border: "1px solid rgba(245, 158, 11, 0.3)",
                                color: "var(--color-sentinel-amber)",
                              }}
                            >
                              <span>{moduleEmojis[mod.module_type] || "\u2699\uFE0F"}</span>
                              {mod.module_type.toUpperCase()}
                            </span>
                          ))
                      ) : (
                        <span style={{ color: "var(--color-sentinel-text-disabled)" }}>
                          No modules active
                        </span>
                      )}
                    </div>
                  </div>

                  <div>
                    <div
                      className="font-medium mb-1"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      Key Capabilities
                    </div>
                    <ul
                      className="space-y-1"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      <li className="flex items-start gap-2">
                        <span style={{ color: "var(--color-sentinel-amber)" }}>&#8226;</span>
                        Natural language queries across building data
                      </li>
                      <li className="flex items-start gap-2">
                        <span style={{ color: "var(--color-sentinel-amber)" }}>&#8226;</span>
                        Predictive maintenance with failure forecasting
                      </li>
                      <li className="flex items-start gap-2">
                        <span style={{ color: "var(--color-sentinel-amber)" }}>&#8226;</span>
                        Anomaly detection with contextual analysis
                      </li>
                      <li className="flex items-start gap-2">
                        <span style={{ color: "var(--color-sentinel-amber)" }}>&#8226;</span>
                        Cross-site pattern recognition
                      </li>
                    </ul>
                  </div>

                  {/* Quick Links */}
                  <div
                    className="pt-2"
                    style={{ borderTop: "1px solid var(--color-sentinel-border)" }}
                  >
                    <div
                      className="font-medium mb-2"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      Quick Links
                    </div>
                    <a
                      href="/docs/sentinel-equipment-reference.html"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-2 py-1 px-2 rounded transition-colors hover:bg-opacity-50"
                      style={{
                        color: "var(--color-sentinel-text-secondary)",
                        background: "transparent",
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.background = "var(--color-sentinel-bg-panel)"}
                      onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
                    >
                      <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      <span>Equipment Reference</span>
                    </a>
                  </div>

                  <div
                    className="pt-2"
                    style={{ borderTop: "1px solid var(--color-sentinel-border)" }}
                  >
                    <p style={{ color: "var(--color-sentinel-text-disabled)", fontSize: "10px" }}>
                      Transforming reactive maintenance into predictive asset protection.
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </nav>

        {/* Footer */}
        <div
          className="flex-none p-4"
          style={{ borderTop: "1px solid var(--color-sentinel-border)" }}
        >
          <div
            className={`text-xs text-center md:hidden ${isCollapsed ? 'lg:hidden' : 'lg:block'}`}
            style={{ color: "var(--color-sentinel-text-disabled)" }}
          >
            <span style={{ color: "var(--color-sentinel-amber)" }}>SENTINEL</span> v{version || "13.0"}
          </div>
          <div className="hidden md:flex lg:hidden justify-center">
            <div
              className="w-2 h-2 rounded-full pulse-live"
              style={{ background: "var(--color-sentinel-amber)" }}
            />
          </div>
        </div>
      </aside>
    </>
  );
}

export default Sidebar;
