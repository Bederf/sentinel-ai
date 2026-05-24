/**
 * Sidebar Navigation Component - SENTINEL Branding
 *
 * Simplified sidebar with 4 items + About section:
 * - Dashboard, AI Chat, SIMBIOT, Settings
 * All site-specific views are now in the building detail tab bar.
 */

import { useState, useMemo, useEffect, useRef } from "react";
import {
  Menu,
  X,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  Info,
  Activity,
  Brain,
  Bell,
  Plug,
  Cpu,
  FileText,
  Wrench,
  Thermometer,
  Zap,
  Lightbulb,
  Sun,
  Droplets,
  Flame,
  Shield,
  Box,
  Gauge,
  DollarSign,
  Leaf,
} from "lucide-react";
import { useModules } from "../contexts/ModuleHooks";
import {
  type View,
  BASE_NAV_ITEMS,
  ADMIN_NAV_ITEMS,
  ADDON_NAV_ITEMS,
} from "../lib/navigation";
import type { NavItem } from "../lib/navigation";
import { getAllowedViews, isRestrictedDemoUser } from "../lib/access-control";

export type { View } from "../lib/navigation";

interface SidebarProps {
  currentView: View;
  onViewChange: (view: View) => void;
  version?: string;
  userRole?: string;
  userEmail?: string;
}

export function Sidebar({ currentView, onViewChange, version = "13.0", userRole, userEmail }: SidebarProps) {
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [isAboutOpen, setIsAboutOpen] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(true); // Start minimized
  const [isMobile, setIsMobile] = useState(false);

  const { activeModules } = useModules();
  const aboutBtnRef = useRef<HTMLDivElement>(null);

  // Detect mobile screen size
  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 768);
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const isAdmin = userRole === 'admin';
  const isDemoUser = userEmail ? isRestrictedDemoUser(userEmail) : false;

  // isCollapsed: always true on mobile (sidebar auto-collapses), otherwise user preference
  const effectiveCollapsed = isMobile ? true : isCollapsed;

  // Build the full nav item list: base + admin/profile-driven add-ons + conditional add-ons
  const allNavItems = useMemo(() => {
    // Base items — filter out any with requiredModule that isn't active
    const items: NavItem[] = BASE_NAV_ITEMS.filter(item => {
      if (!item.requiredModule) return true;
      return activeModules.some(
        m => m.module_type === item.requiredModule && m.status === 'active'
      );
    });

    // Admin-only items (SIMBIOT, Settings)
    if (isAdmin || isDemoUser) {
      items.push(...ADMIN_NAV_ITEMS);
    }

    // Conditional add-on items (only if their module is active)
    for (const item of ADDON_NAV_ITEMS) {
      if (item.requiredModule) {
        const moduleActive = activeModules.some(
          m => m.module_type === item.requiredModule && m.status === 'active'
        );
        if (moduleActive) {
          items.push(item);
        }
      } else {
        items.push(item);
      }
    }

    // Apply access control filtering
    if (!userEmail) return items;
    const allowed = getAllowedViews(userEmail, items.map(i => i.id));
    return items.filter(item => allowed.includes(item.id));
  }, [userEmail, isAdmin, isDemoUser, activeModules]);

  const handleNavClick = (view: View) => {
    onViewChange(view);
    setIsMobileOpen(false);
  };

  const renderNavItem = (item: NavItem, isActive: boolean) => {
    const Icon = item.icon;

    return (
      <div key={item.id} className="relative group">
        <button
          onClick={() => handleNavClick(item.id)}
          className={`
            w-full flex items-center gap-3 px-4 py-3 mb-1 mx-auto
            transition-all duration-150 ease-in-out
            ${effectiveCollapsed ? "justify-center" : "justify-start"}
            hover:brightness-110
            ${!isActive ? 'hover:bg-white/5' : ''}
          `}
          style={{
            background: isActive
              ? 'color-mix(in oklch, var(--color-sentinel-amber) 15%, transparent)'
              : "transparent",
            borderLeft: isActive
              ? "4px solid var(--color-sentinel-amber)"
              : "4px solid transparent",
            color: isActive
              ? "var(--color-sentinel-text-primary)"
              : "var(--color-sentinel-text-secondary)",
            boxShadow: isActive
              ? "0 0 20px color-mix(in oklch, var(--color-sentinel-amber) 25%, transparent), inset 0 0 12px color-mix(in oklch, var(--color-sentinel-amber) 10%, transparent)"
              : "none",
          }}
          aria-current={isActive ? "page" : undefined}
          aria-label={item.label}
        >
          <Icon
            className={`flex-shrink-0 ${isActive ? 'font-bold' : ''}`}
            style={{
              width: isMobile ? '22px' : '20px',
              height: isMobile ? '22px' : '20px',
              color: isActive
                ? "var(--color-sentinel-amber)"
                : "var(--color-sentinel-text-secondary)",
              filter: isActive
                ? "brightness(1.2) drop-shadow(0 0 4px color-mix(in oklch, var(--color-sentinel-amber) 50%, transparent))"
                : "brightness(1.1)",
            }}
          />
          {/* Always show labels on mobile, or when not collapsed on desktop */}
          <div className={`flex flex-col items-start flex-1 ${(effectiveCollapsed && !isMobile) ? "hidden" : "flex"}`}>
            <span
              className={`font-medium ${isMobile ? 'text-base' : 'text-sm'}`}
              style={{
                color: "var(--color-sentinel-text-primary)",
                fontWeight: isActive ? '600' : '500',
              }}
            >
              {item.label}
            </span>
            {item.description && !isMobile && (
              <span
                className="text-xs"
                style={{
                  color: "var(--color-sentinel-text-secondary)",
                  opacity: 0.8,
                }}
              >
                {item.description}
              </span>
            )}
          </div>
        </button>
      </div>
    );
  };

  // Module icon mapping for About section \u2014 Lucide icons with aria-label text equivalents
  const moduleIcons: Record<string, { icon: React.ComponentType<{ className?: string }>; label: string }> = {
    kpi:               { icon: Activity,    label: "KPI" },
    ml:                { icon: Brain,       label: "ML" },
    notifications:     { icon: Bell,        label: "Notifications" },
    integrations:      { icon: Plug,        label: "Integrations" },
    simbiot:           { icon: Cpu,         label: "SIMBIOT" },
    logging:           { icon: FileText,    label: "Logging" },
    assets:            { icon: Wrench,      label: "Assets" },
    hvac:              { icon: Thermometer, label: "HVAC" },
    energy:            { icon: Zap,         label: "Energy" },
    lighting:          { icon: Lightbulb,   label: "Lighting" },
    solar:             { icon: Sun,         label: "Solar" },
    water:             { icon: Droplets,    label: "Water" },
    fire:              { icon: Flame,       label: "Fire" },
    security:          { icon: Shield,       label: "Security" },
    digital_twin:      { icon: Box,         label: "Digital Twin" },
    hvac_control:      { icon: Thermometer, label: "HVAC Control" },
    energy_control:    { icon: Zap,         label: "Energy Control" },
    lighting_control:  { icon: Lightbulb,   label: "Lighting Control" },
    solar_control:     { icon: Sun,         label: "Solar Control" },
    water_control:     { icon: Droplets,    label: "Water Control" },
    security_control:  { icon: Shield,       label: "Security Control" },
    digital_twin_control: { icon: Box,      label: "Digital Twin Control" },
    maintenance:       { icon: Wrench,      label: "Maintenance" },
    financial:         { icon: DollarSign,  label: "Financial" },
    compliance:        { icon: Leaf,        label: "Compliance" },
    fleet_ml:          { icon: Brain,       label: "Fleet ML" },
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
          <X className="h-5 w-5" style={{ color: "var(--color-sentinel-text-primary)" }} />
        ) : (
          <Menu className="h-5 w-5" style={{ color: "var(--color-sentinel-text-primary)" }} />
        )}
      </button>

      {/* Mobile overlay */}
      {isMobileOpen && (
        <div
          className="md:hidden fixed inset-0 z-30 animate-in fade-in duration-200"
          style={{ background: "color-mix(in oklch, #000 75%, transparent)" }}
          onClick={() => setIsMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed md:relative inset-y-0 left-0 z-40
          ${isMobile ? 'w-[85%] max-w-sm' : isCollapsed ? 'w-16' : 'w-64'}
          ${!isMobile && isCollapsed ? 'md:w-16' : ''}
          ${!isMobile && !isCollapsed ? 'md:w-56' : ''}
          transform transition-all duration-200 ease-in-out
          ${isMobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}
          flex flex-col
        `}
        style={{
          transition: 'width 200ms ease-out',
          willChange: 'width',
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
            className={`hidden md:flex absolute top-2 transition-all duration-200 ${
              isCollapsed
                ? 'left-1/2 -translate-x-1/2'
                : 'right-2'
            }`}
            aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            <span
              className="inline-flex items-center justify-center h-8 w-8 rounded-full transition-all duration-200 hover:scale-110 hover:brightness-125"
              style={{
                background: 'color-mix(in oklch, var(--color-sentinel-amber) 12%, transparent)',
                border: '1px solid color-mix(in oklch, var(--color-sentinel-amber) 35%, transparent)',
                color: 'var(--color-sentinel-text-secondary)',
              }}
            >
              {isCollapsed ? (
                <ChevronRight className="h-4 w-4" />
              ) : (
                <ChevronLeft className="h-4 w-4" />
              )}
            </span>
          </button>
        </div>

        {/* Navigation items */}
        <nav className="flex-1 py-4 overflow-y-auto" role="navigation">
          {/* Menu label */}
          <div className="px-3 mb-2">
            <span
              className={`text-xs font-medium uppercase tracking-wider md:hidden ${isCollapsed ? 'lg:hidden' : 'lg:block'}`}
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            >
              Menu
            </span>
          </div>

          {allNavItems.map((item) =>
            renderNavItem(item, currentView === item.id)
          )}

          {/* About Section */}
          <div
            ref={aboutBtnRef}
            className="mt-4 pt-4 mx-3 relative"
            style={{ borderTop: "1px solid var(--color-sentinel-border)" }}
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
              <span className={`font-medium text-sm ${isCollapsed ? "hidden" : "block"} flex-1 text-left`}>About</span>
              {!isCollapsed && (isAboutOpen ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              ))}
            </button>

            {/* Expandable about section */}
            {isAboutOpen && (
              <div
                className={`mt-2 md:block ${
                  isCollapsed
                    ? "fixed z-50 w-72 max-h-96 overflow-y-auto"
                    : "relative"
                }`}
                /* eslint-disable react-hooks/refs */
                style={isCollapsed && aboutBtnRef.current ? {
                  left: aboutBtnRef.current.getBoundingClientRect().right + 12,
                  bottom: Math.max(8, window.innerHeight - aboutBtnRef.current.getBoundingClientRect().bottom),
                } : undefined}
                /* eslint-enable react-hooks/refs */
              >
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
                                background: 'color-mix(in oklch, var(--color-sentinel-amber) 12%, transparent)',
                                border: '1px solid color-mix(in oklch, var(--color-sentinel-amber) 30%, transparent)',
                                color: 'var(--color-sentinel-amber)',
                              }}
                              aria-label={moduleIcons[mod.module_type]?.label ?? mod.module_type}
                            >
                              {(() => {
                                const entry = moduleIcons[mod.module_type] ?? { icon: Gauge, label: mod.module_type };
                                const Icon = entry.icon;
                                return <Icon className="w-3 h-3" aria-hidden="true" />;
                              })()}
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

        {/* Footer - version info hidden on mobile */}
        <div
          className="flex-none p-4 hidden md:block"
          style={{ borderTop: "1px solid var(--color-sentinel-border)" }}
        >
          <div
            className={`text-[9px] leading-tight text-center ${isCollapsed ? 'lg:block' : 'lg:block'}`}
            style={{
              color: "var(--color-sentinel-text-disabled)",
              whiteSpace: 'normal',
              wordBreak: 'break-word',
            }}
          >
            {!isCollapsed && (
              <span style={{ color: "var(--color-sentinel-amber)" }}>
                SENTINEL v{version || "13.0"}
              </span>
            )}
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
