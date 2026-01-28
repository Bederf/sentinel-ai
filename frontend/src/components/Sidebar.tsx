/**
 * Sidebar Navigation Component - SENTINEL Branding
 *
 * Features:
 * - SENTINEL shield logo with amber accent
 * - Dark panel design with amber accent indicators
 * - Navigation items: Dashboard, Chat
 * - Data Upload section for CSV files
 * - Lucide icons with SENTINEL styling
 * - Collapsible on mobile (hamburger menu)
 * - Active view highlighting with left border accent
 */

import { useState, useRef } from "react";
import {
  MessageSquare,
  LayoutDashboard,
  Menu,
  X,
  Upload,
  FileUp,
  Check,
  AlertCircle,
  Database,
  Shield,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  Info,
  ClipboardList,
  Settings as SettingsIcon,
  Zap,
} from "lucide-react";

export type View = "dashboard" | "chat" | "control" | "control-audit" | "optimization" | "upload" | "settings";

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

interface DataStatus {
  work_orders: number;
  assets: number;
  sites: number;
  total_cost: number;
  total_contract_value: number;
}

const navItems: NavItem[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard, description: "System overview" },
  { id: "chat", label: "Chat", icon: MessageSquare, description: "AI Assistant" },
  { id: "optimization", label: "Optimization", icon: Zap, description: "Load Shedding AI" },
  { id: "control", label: "Control", icon: Shield, description: "Building Controls" },
  { id: "control-audit", label: "Control Audit", icon: ClipboardList, description: "Control System Logs" },
  { id: "settings", label: "Settings", icon: SettingsIcon, description: "System Configuration" },
];

const uploadTypes = [
  { id: "work_orders", label: "Work Orders", description: "CAFM work order history" },
  { id: "assets", label: "Assets", description: "Asset register with lifecycle" },
  { id: "sites", label: "Sites", description: "Site information & contracts" },
  { id: "alarms", label: "Alarms", description: "BCC alarm history" },
  { id: "energy_readings", label: "Energy", description: "Utility consumption data" },
  { id: "generator_telemetry", label: "Generator", description: "DeepSea controller data" },
  { id: "hvac_telemetry", label: "HVAC", description: "BACnet AHU/chiller data" },
  { id: "vsd_telemetry", label: "VSD", description: "Danfoss/ABB drive data" },
  { id: "chiller_telemetry", label: "Chiller", description: "York/Carrier/Trane data" },
  { id: "pump_telemetry", label: "Pump", description: "Grundfos/KSB pump data" },
];

export function Sidebar({ currentView, onViewChange, version = "1.0" }: SidebarProps) {
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isAboutOpen, setIsAboutOpen] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(true); // Start minimized
  const [uploadStatus, setUploadStatus] = useState<Record<string, "idle" | "uploading" | "success" | "error">>({});
  const [dataStatus, setDataStatus] = useState<DataStatus | null>(null);
  const fileInputRefs = useRef<Record<string, HTMLInputElement | null>>({});

  const handleNavClick = (view: View) => {
    onViewChange(view);
    setIsMobileOpen(false);
  };

  const fetchDataStatus = async () => {
    try {
      const response = await fetch("/api/data-status");
      if (response.ok) {
        const data = await response.json();
        setDataStatus(data);
      }
    } catch (error) {
      console.error("Failed to fetch data status:", error);
    }
  };

  const handleUploadClick = (typeId: string) => {
    fileInputRefs.current[typeId]?.click();
  };

  const handleFileChange = async (typeId: string, event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setUploadStatus((prev) => ({ ...prev, [typeId]: "uploading" }));

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch(`/api/upload/${typeId}`, {
        method: "POST",
        body: formData,
      });

      if (response.ok) {
        setUploadStatus((prev) => ({ ...prev, [typeId]: "success" }));
        fetchDataStatus();
        setTimeout(() => {
          setUploadStatus((prev) => ({ ...prev, [typeId]: "idle" }));
        }, 3000);
      } else {
        setUploadStatus((prev) => ({ ...prev, [typeId]: "error" }));
      }
    } catch (error) {
      console.error("Upload failed:", error);
      setUploadStatus((prev) => ({ ...prev, [typeId]: "error" }));
    }

    event.target.value = "";
  };

  const toggleUploadSection = () => {
    setIsUploadOpen(!isUploadOpen);
    if (!isUploadOpen) {
      fetchDataStatus();
    }
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
                onClick={() => handleNavClick(item.id)}
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

          {/* Data Upload Section */}
          <div
            className="mt-4 pt-4 mx-3"
            style={{ borderTop: "1px solid var(--color-grafana-border)" }}
          >
            <button
              onClick={toggleUploadSection}
              className={`w-full flex items-center gap-3 px-1 py-2 transition-all duration-150 md:justify-center ${isCollapsed ? 'lg:justify-center' : 'lg:justify-start'}`}
              style={{
                color: isUploadOpen
                  ? "var(--color-sentinel-text-primary)"
                  : "var(--color-sentinel-text-secondary)",
              }}
            >
              <Database
                className="h-5 w-5 flex-shrink-0"
                style={{
                  color: isUploadOpen ? "var(--color-sentinel-blue)" : "var(--color-sentinel-text-secondary)",
                }}
              />
              <span className={`font-medium text-sm md:hidden ${isCollapsed ? 'lg:hidden' : 'lg:block'} flex-1 text-left`}>Data Sources</span>
              {isUploadOpen ? (
                <ChevronDown className={`h-4 w-4 md:hidden ${isCollapsed ? 'lg:hidden' : 'lg:block'}`} />
              ) : (
                <ChevronRight className={`h-4 w-4 md:hidden ${isCollapsed ? 'lg:hidden' : 'lg:block'}`} />
              )}
            </button>

            {/* Expandable upload section */}
            {isUploadOpen && (
              <div className={`mt-2 space-y-1 md:hidden ${isCollapsed ? 'lg:hidden' : 'lg:block'}`}>
                {/* Data status summary */}
                {dataStatus && (
                  <div
                    className="rounded p-3 text-xs space-y-1 mb-3"
                    style={{
                      background: "var(--color-sentinel-bg-secondary)",
                      border: "1px solid var(--color-sentinel-border)",
                    }}
                  >
                    <div
                      className="font-medium mb-2"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      Current Data
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <span style={{ color: "var(--color-sentinel-text-disabled)" }}>Work Orders</span>
                        <div style={{ color: "var(--color-sentinel-blue)" }}>{dataStatus.work_orders}</div>
                      </div>
                      <div>
                        <span style={{ color: "var(--color-sentinel-text-disabled)" }}>Assets</span>
                        <div style={{ color: "var(--color-sentinel-blue)" }}>{dataStatus.assets}</div>
                      </div>
                      <div>
                        <span style={{ color: "var(--color-sentinel-text-disabled)" }}>Sites</span>
                        <div style={{ color: "var(--color-sentinel-blue)" }}>{dataStatus.sites}</div>
                      </div>
                      <div>
                        <span style={{ color: "var(--color-sentinel-text-disabled)" }}>Total Cost</span>
                        <div style={{ color: "var(--color-sentinel-green)" }}>
                          R{dataStatus.total_cost.toLocaleString()}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Upload buttons - Compact grid */}
                <div className="grid grid-cols-2 gap-1">
                  {uploadTypes.map((type) => {
                    const status = uploadStatus[type.id] || "idle";

                    return (
                      <div key={type.id} className="relative">
                        <input
                          type="file"
                          accept=".csv"
                          className="hidden"
                          ref={(el) => (fileInputRefs.current[type.id] = el)}
                          onChange={(e) => handleFileChange(type.id, e)}
                        />
                        <button
                          onClick={() => handleUploadClick(type.id)}
                          disabled={status === "uploading"}
                          className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded text-xs transition-all duration-150"
                          style={{
                            background:
                              status === "success"
                                ? "rgba(115, 191, 105, 0.15)"
                                : status === "error"
                                  ? "rgba(242, 73, 92, 0.15)"
                                  : status === "uploading"
                                    ? "rgba(50, 116, 217, 0.15)"
                                    : "var(--color-grafana-bg-secondary)",
                            border: `1px solid ${
                              status === "success"
                                ? "rgba(115, 191, 105, 0.3)"
                                : status === "error"
                                  ? "rgba(242, 73, 92, 0.3)"
                                  : status === "uploading"
                                    ? "rgba(50, 116, 217, 0.3)"
                                    : "var(--color-grafana-border)"
                            }`,
                            color:
                              status === "success"
                                ? "var(--color-status-success)"
                                : status === "error"
                                  ? "var(--color-status-error)"
                                  : status === "uploading"
                                    ? "var(--color-grafana-blue)"
                                    : "var(--color-grafana-text-secondary)",
                          }}
                        >
                          {status === "success" ? (
                            <Check className="h-3 w-3" />
                          ) : status === "error" ? (
                            <AlertCircle className="h-3 w-3" />
                          ) : status === "uploading" ? (
                            <Upload className="h-3 w-3 animate-pulse" />
                          ) : (
                            <FileUp className="h-3 w-3" />
                          )}
                          <span className="truncate">{type.label}</span>
                        </button>
                      </div>
                    );
                  })}
                </div>

                {/* Reload data button */}
                <button
                  onClick={async () => {
                    await fetch("/api/reload-data", { method: "POST" });
                    fetchDataStatus();
                  }}
                  className="w-full mt-2 px-3 py-2 text-xs rounded transition-colors"
                  style={{
                    color: "var(--color-grafana-text-disabled)",
                    background: "transparent",
                    border: "1px dashed var(--color-grafana-border)",
                  }}
                >
                  Reload All Data
                </button>
              </div>
            )}
          </div>

          {/* About Section */}
          <div
            className="mt-4 pt-4 mx-3"
            style={{ borderTop: "1px solid var(--color-grafana-border)" }}
          >
            <button
              onClick={() => setIsAboutOpen(!isAboutOpen)}
              className="w-full flex items-center gap-3 px-1 py-2 transition-all duration-150 md:justify-center lg:justify-start"
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
              <span className="font-medium text-sm md:hidden lg:block flex-1 text-left">About</span>
              {isAboutOpen ? (
                <ChevronDown className="h-4 w-4 md:hidden lg:block" />
              ) : (
                <ChevronRight className="h-4 w-4 md:hidden lg:block" />
              )}
            </button>

            {/* Expandable about section */}
            {isAboutOpen && (
              <div className="mt-2 md:hidden lg:block">
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
