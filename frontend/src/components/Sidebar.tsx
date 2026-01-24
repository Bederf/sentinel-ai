/**
 * Sidebar Navigation Component
 *
 * Features:
 * - Navigation items: Chat, Dashboard
 * - Data Upload section for CSV files
 * - Lucide icons for each item
 * - Collapsible on mobile (hamburger menu)
 * - Active view highlighting
 * - Professional blue/gray FM theme
 */

import { useState, useRef } from "react";
import { MessageSquare, LayoutDashboard, Menu, X, Upload, FileUp, Check, AlertCircle, Database } from "lucide-react";

export type View = "dashboard" | "chat" | "upload";

interface SidebarProps {
  currentView: View;
  onViewChange: (view: View) => void;
}

interface NavItem {
  id: View;
  label: string;
  icon: typeof MessageSquare;
}

interface DataStatus {
  work_orders: number;
  assets: number;
  sites: number;
  total_cost: number;
  total_contract_value: number;
}

const navItems: NavItem[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "chat", label: "Chat", icon: MessageSquare },
];

const uploadTypes = [
  { id: "work_orders", label: "Work Orders", description: "CAFM work order history" },
  { id: "assets", label: "Assets", description: "Asset register with lifecycle" },
  { id: "sites", label: "Sites", description: "Site information & contracts" },
  { id: "alarms", label: "Alarms", description: "BCC alarm history" },
  { id: "energy_readings", label: "Energy", description: "Utility consumption data" },
  { id: "generator_telemetry", label: "Generator Telemetry", description: "DeepSea controller data" },
  { id: "hvac_telemetry", label: "HVAC Telemetry", description: "BACnet AHU/chiller data" },
  { id: "vsd_telemetry", label: "VSD Telemetry", description: "Danfoss/ABB drive data" },
  { id: "chiller_telemetry", label: "Chiller Telemetry", description: "York/Carrier/Trane data" },
  { id: "pump_telemetry", label: "Pump Telemetry", description: "Grundfos/KSB pump data" },
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
        // Reset after 3 seconds
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

    // Clear the input
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
        className="md:hidden fixed top-4 left-4 z-50 p-2 bg-white rounded-lg shadow-md border border-gray-200 hover:bg-gray-50 transition-colors"
        aria-label={isMobileOpen ? "Close menu" : "Open menu"}
      >
        {isMobileOpen ? (
          <X className="h-5 w-5 text-gray-600" />
        ) : (
          <Menu className="h-5 w-5 text-gray-600" />
        )}
      </button>

      {/* Mobile overlay */}
      {isMobileOpen && (
        <div
          className="md:hidden fixed inset-0 bg-black/30 z-30"
          onClick={() => setIsMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed md:relative inset-y-0 left-0 z-40
          w-64 md:w-20 lg:w-64
          bg-white border-r border-gray-200
          transform transition-transform duration-200 ease-in-out
          ${isMobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}
          flex flex-col
          shadow-xl md:shadow-none
        `}
      >
        {/* Logo area */}
        <div className="flex-none h-[73px] flex items-center justify-center border-b border-gray-200 md:block hidden">
          <div className="flex items-center gap-2 px-4">
            <div className="w-8 h-8 bg-bidvest-blue-600 rounded-lg flex items-center justify-center">
              <LayoutDashboard className="h-5 w-5 text-white" />
            </div>
            <span className="font-semibold text-gray-900 hidden lg:block">BMS</span>
          </div>
        </div>

        {/* Navigation items */}
        <nav className="flex-1 p-4 space-y-2 mt-16 md:mt-0 overflow-y-auto" role="navigation">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentView === item.id;

            return (
              <button
                key={item.id}
                onClick={() => handleNavClick(item.id)}
                className={`
                  w-full flex items-center gap-3 px-4 py-3 rounded-lg
                  transition-all duration-150 ease-in-out
                  ${
                    isActive
                      ? "bg-bidvest-blue-50 text-bidvest-blue-700 border border-bidvest-blue-200"
                      : "text-gray-600 hover:bg-gray-50 hover:text-gray-900 border border-transparent"
                  }
                `}
                aria-current={isActive ? "page" : undefined}
              >
                <Icon
                  className={`h-5 w-5 flex-shrink-0 ${
                    isActive ? "text-bidvest-blue-600" : "text-gray-400"
                  }`}
                />
                <span className="font-medium md:hidden lg:block">{item.label}</span>
              </button>
            );
          })}

          {/* Upload Section */}
          <div className="pt-4 border-t border-gray-200 mt-4">
            <button
              onClick={toggleUploadSection}
              className={`
                w-full flex items-center gap-3 px-4 py-3 rounded-lg
                transition-all duration-150 ease-in-out
                ${isUploadOpen
                  ? "bg-green-50 text-green-700 border border-green-200"
                  : "text-gray-600 hover:bg-gray-50 hover:text-gray-900 border border-transparent"
                }
              `}
            >
              <Database className={`h-5 w-5 flex-shrink-0 ${isUploadOpen ? "text-green-600" : "text-gray-400"}`} />
              <span className="font-medium md:hidden lg:block">Data Upload</span>
            </button>

            {/* Expandable upload section */}
            {isUploadOpen && (
              <div className="mt-2 space-y-2 pl-2">
                {/* Data status summary */}
                {dataStatus && (
                  <div className="bg-gray-50 rounded-lg p-3 text-xs space-y-1 mb-3">
                    <div className="font-medium text-gray-700">Current Data:</div>
                    <div className="text-gray-600">Work Orders: {dataStatus.work_orders}</div>
                    <div className="text-gray-600">Assets: {dataStatus.assets}</div>
                    <div className="text-gray-600">Sites: {dataStatus.sites}</div>
                    <div className="text-gray-600">Total Cost: R{dataStatus.total_cost.toLocaleString()}</div>
                  </div>
                )}

                {/* Upload buttons */}
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
                        className={`
                          w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm
                          transition-all duration-150
                          ${status === "success"
                            ? "bg-green-100 text-green-700 border border-green-200"
                            : status === "error"
                            ? "bg-red-100 text-red-700 border border-red-200"
                            : status === "uploading"
                            ? "bg-blue-100 text-blue-700 border border-blue-200"
                            : "bg-white text-gray-600 border border-gray-200 hover:bg-gray-50"
                          }
                        `}
                      >
                        {status === "success" ? (
                          <Check className="h-4 w-4" />
                        ) : status === "error" ? (
                          <AlertCircle className="h-4 w-4" />
                        ) : status === "uploading" ? (
                          <Upload className="h-4 w-4 animate-pulse" />
                        ) : (
                          <FileUp className="h-4 w-4" />
                        )}
                        <div className="flex-1 text-left">
                          <div className="font-medium">{type.label}</div>
                          <div className="text-xs opacity-70 hidden lg:block">{type.description}</div>
                        </div>
                      </button>
                    </div>
                  );
                })}

                {/* Reload data button */}
                <button
                  onClick={async () => {
                    await fetch("/api/reload-data", { method: "POST" });
                    fetchDataStatus();
                  }}
                  className="w-full mt-2 px-3 py-2 text-xs text-gray-500 hover:text-gray-700 hover:bg-gray-50 rounded-md transition-colors"
                >
                  Reload All Data
                </button>
              </div>
            )}
          </div>
        </nav>

        {/* Footer */}
        <div className="flex-none p-4 border-t border-gray-200">
          <div className="text-xs text-gray-400 text-center md:hidden lg:block">
            FM Assistant v1.0
          </div>
        </div>
      </aside>
    </>
  );
}

export default Sidebar;
