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
} from "lucide-react";

export type View = "dashboard" | "chat" | "upload";

interface SidebarProps {
  currentView: View;
  onViewChange: (view: View) => void;
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

export function Sidebar({ currentView, onViewChange }: SidebarProps) {
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
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
          w-64 md:w-16 lg:w-56
          transform transition-transform duration-200 ease-in-out
          ${isMobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}
          flex flex-col
        `}
        style={{
          background: "var(--color-grafana-bg-primary)",
          borderRight: "1px solid var(--color-grafana-border)",
        }}
      >
        {/* SENTINEL Logo area */}
        <div
          className="flex-none h-16 flex items-center px-4 md:justify-center lg:justify-start"
          style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
        >
          <div className="flex items-center gap-3">
            {/* SENTINEL Shield Logo */}
            <div
              className="w-9 h-9 rounded-lg flex items-center justify-center sentinel-shield sentinel-shield-active"
            >
              <Shield className="h-5 w-5" style={{ color: "var(--color-sentinel-amber)" }} />
            </div>
            <div className="md:hidden lg:block">
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
        </div>

        {/* Navigation items */}
        <nav className="flex-1 py-4 overflow-y-auto" role="navigation">
          <div className="px-3 mb-2">
            <span
              className="text-xs font-medium uppercase tracking-wider md:hidden lg:block"
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
                <div className="flex flex-col items-start md:hidden lg:flex">
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
              className="w-full flex items-center gap-3 px-1 py-2 transition-all duration-150 md:justify-center lg:justify-start"
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
              <span className="font-medium text-sm md:hidden lg:block flex-1 text-left">Data Sources</span>
              {isUploadOpen ? (
                <ChevronDown className="h-4 w-4 md:hidden lg:block" />
              ) : (
                <ChevronRight className="h-4 w-4 md:hidden lg:block" />
              )}
            </button>

            {/* Expandable upload section */}
            {isUploadOpen && (
              <div className="mt-2 space-y-1 md:hidden lg:block">
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
        </nav>

        {/* Footer */}
        <div
          className="flex-none p-4"
          style={{ borderTop: "1px solid var(--color-sentinel-border)" }}
        >
          <div
            className="text-xs text-center md:hidden lg:block"
            style={{ color: "var(--color-sentinel-text-disabled)" }}
          >
            <span style={{ color: "var(--color-sentinel-amber)" }}>SENTINEL</span> v1.0
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
