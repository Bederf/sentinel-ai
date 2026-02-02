/**
 * Sidebar Navigation Component - SENTINEL Branding
 *
 * Features:
 * - SENTINEL shield logo with amber accent
 * - Dark panel design with amber accent indicators
 * - Navigation items: Dashboard, Chat, Integrations, etc.
 * - Lucide icons with SENTINEL styling
 * - Collapsible on mobile (hamburger menu)
 * - Active view highlighting with left border accent
 */

import { useState } from "react";
import {
  MessageSquare,
  LayoutDashboard,
  Menu,
  X,
  Shield,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  Info,
  ClipboardList,
  Settings as SettingsIcon,
  Zap,
  Wrench,
  Activity,
  Users,
  LayoutGrid,
} from "lucide-react";

export type View = "dashboard" | "chat" | "technician" | "control" | "control-audit" | "optimization" | "settings" | "integrations" | "occupancy";

interface SidebarProps {
  currentView: View;
  onViewChange: (view: View) => void;
  version?: string;
  onCustomizeDashboard?: () => void;
}

interface SidebarProps {
  currentView: View;
  onViewChange: (view: View) => void;
  version?: string;
}

interface NavItem {
  id: View;
  label: string;
  icon: typeof MessageSquare;
  description?: string;
}

const navItems: NavItem[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard, description: "System overview" },
  { id: "chat", label: "Chat", icon: MessageSquare, description: "AI Assistant" },
  { id: "technician", label: "Tech Chat", icon: Wrench, description: "Fault Diagnosis" },
  { id: "optimization", label: "Optimization", icon: Zap, description: "Load Shedding AI" },
  { id: "occupancy", label: "Occupancy", icon: Users, description: "DALI Lighting" },
  { id: "control", label: "Control", icon: Shield, description: "Building Controls" },
  { id: "control-audit", label: "Control Audit", icon: ClipboardList, description: "Control System Logs" },
  { id: "settings", label: "Settings", icon: SettingsIcon, description: "System Configuration" },
  { id: "integrations", label: "Integrations", icon: Activity, description: "BMS Integration Health" },
];

export function Sidebar({ currentView, onViewChange, version = "1.0", onCustomizeDashboard }: SidebarProps) {
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [isAboutOpen, setIsAboutOpen] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(true); // Start minimized

  const handleNavClick = (view: View) => {
    onViewChange(view);
    setIsMobileOpen(false);
  };

  return (
    <>
      {/* Mobile hamburger button */}
      <button
        onClick={() => setIsMobileOpen(!isMobileOpen)}
        className="md:hidden fixed top-4 left-4 z-50 p-2 rounded-md transition-colors"
        style={{
          background: "var(--color-grafana-bg-secondary)",
          border: "1px solid var(--color-grafana-border)",
        }}
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
          background: "var(--color-grafana-bg-primary)",
          borderRight: "1px solid var(--color-grafana-border)",
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
          {/* Toggle button - moves with sidebar state, only visible on large screens */}
          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className={`hidden lg:flex absolute top-1/2 transform -translate-y-1/2 p-1 rounded hover:bg-sentinel-bg-secondary transition-all duration-200 ${
              isCollapsed 
                ? 'left-1/2 -translate-x-1/2' 
                : 'right-2'
            }`}
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
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
          <div className="px-3 mb-2">
            <span
              className={`text-xs font-medium uppercase tracking-wider md:hidden ${isCollapsed ? 'lg:hidden' : 'lg:block'}`}
              style={{ color: "var(--color-grafana-text-disabled)" }}
            >
              Menu
            </span>
          </div>

          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentView === item.id;

            return (
              <button
                key={item.id}
                onClick={() => {
                  // Always navigate to the selected view, even if already active
                  handleNavClick(item.id);
                }}
                className={`
                  w-full flex items-center gap-3 px-4 py-2.5 mb-1 mx-auto
                  transition-all duration-150 ease-in-out
                  md:justify-center lg:justify-start
                `}
                style={{
                  background: isActive ? "var(--color-sentinel-bg-secondary)" : "transparent",
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
                <div className={`flex flex-col items-start md:hidden ${isCollapsed ? 'lg:hidden' : 'lg:flex'}`}>
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
            );
          })}

          {/* Customize Dashboard Button */}
          {onCustomizeDashboard && (
            <div className="mt-4 mx-3">
              <button
                onClick={() => {
                  onCustomizeDashboard();
                  setIsMobileOpen(false);
                }}
                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-150 md:justify-center lg:justify-start"
                style={{
                  background: "rgba(245, 158, 11, 0.1)",
                  border: "1px solid rgba(245, 158, 11, 0.3)",
                  color: "var(--color-sentinel-amber)",
                }}
              >
                <LayoutGrid className="h-5 w-5 flex-shrink-0" />
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
              className={`w-full flex items-center gap-3 px-1 py-2 transition-all duration-150 md:justify-center ${isCollapsed ? 'lg:justify-center' : 'lg:justify-start'}`}
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
                      Key Capabilities
                    </div>
                    <ul
                      className="space-y-1"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      <li className="flex items-start gap-2">
                        <span style={{ color: "var(--color-sentinel-amber)" }}>•</span>
                        Natural language queries across building data
                      </li>
                      <li className="flex items-start gap-2">
                        <span style={{ color: "var(--color-sentinel-amber)" }}>•</span>
                        Predictive maintenance with failure forecasting
                      </li>
                      <li className="flex items-start gap-2">
                        <span style={{ color: "var(--color-sentinel-amber)" }}>•</span>
                        Anomaly detection with contextual analysis
                      </li>
                      <li className="flex items-start gap-2">
                        <span style={{ color: "var(--color-sentinel-amber)" }}>•</span>
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
                      <span>Equipment Reference (PDF)</span>
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
            <span style={{ color: "var(--color-sentinel-amber)" }}>SENTINEL</span> v{version || "1.0"}
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
