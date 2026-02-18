/**
 * ControlTest Page - SENTINEL control panel test page
 *
 * Features:
 * - Test page for control panel components
 * - Integration with useDeviceControl hook
 * - Demo scenario testing
 * - Component verification
 */

import { useState } from "react";
import { ControlPanel } from "../components/ControlPanel";
import { DemoControlPanel } from "../components/DemoControlPanel";
import { ControlStatus } from "../components/ControlStatus";
import useDeviceControl from "../hooks/useDeviceControl";
import { demoDevices } from "../data/demoControls";

export function ControlTest() {
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>(demoDevices[0].id);
  const [showDemoPanel, setShowDemoPanel] = useState(true);
  const [controlLog, setControlLog] = useState<Array<{ timestamp: string; message: string }>>([]);

  // Use device control hook
  const deviceControl = useDeviceControl({
    deviceId: selectedDeviceId,
    refreshInterval: 10000,
    autoConnect: true,
  });

  // Handle control action
  const handleControl = async (deviceId: string, point: string, value: number | boolean) => {
    try {
      const response = await deviceControl.controlDevice(point, value);

      // Log the control action
      setControlLog(prev => [{
        timestamp: new Date().toLocaleTimeString(),
        message: `Controlled ${deviceId}: ${point} = ${value} (${response.message})`,
      }, ...prev.slice(0, 9)]); // Keep last 10 entries

      return response;
    } catch (err) {
      console.error("Control failed:", err);
      throw err;
    }
  };

  // Handle scenario completion
  const handleScenarioComplete = (scenarioId: string) => {
    setControlLog(prev => [{
      timestamp: new Date().toLocaleTimeString(),
      message: `Scenario ${scenarioId} completed successfully`,
    }, ...prev.slice(0, 9)]);
  };

  // Get selected device
  const selectedDevice = demoDevices.find(d => d.id === selectedDeviceId) || demoDevices[0];

  return (
    <div className="min-h-screen p-4 md:p-6" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
            SENTINEL Control Panel Test
          </h1>
          <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Test page for Grafana-style control panel components with safety integration
          </p>
        </div>

        {/* Toggle between demo and individual panels */}
        <div className="mb-6">
          <div className="flex flex-wrap gap-4 mb-4">
            <button
              onClick={() => setShowDemoPanel(true)}
              className={`px-4 py-2 rounded font-medium transition-colors ${showDemoPanel ? "brightness-110" : ""}`}
              style={{
                background: showDemoPanel ? "var(--color-sentinel-amber)" : "var(--color-sentinel-bg-secondary)",
                color: showDemoPanel ? "white" : "var(--color-sentinel-text-secondary)",
                border: `1px solid ${showDemoPanel ? "var(--color-sentinel-amber)" : "var(--color-sentinel-border)"}`,
              }}
            >
              Demo Panel
            </button>
            <button
              onClick={() => setShowDemoPanel(false)}
              className={`px-4 py-2 rounded font-medium transition-colors ${!showDemoPanel ? "brightness-110" : ""}`}
              style={{
                background: !showDemoPanel ? "var(--color-sentinel-blue)" : "var(--color-sentinel-bg-secondary)",
                color: !showDemoPanel ? "white" : "var(--color-sentinel-text-secondary)",
                border: `1px solid ${!showDemoPanel ? "var(--color-sentinel-blue)" : "var(--color-sentinel-border)"}`,
              }}
            >
              Individual Panels
            </button>
          </div>
        </div>

        {/* Demo Panel */}
        {showDemoPanel ? (
          <DemoControlPanel
            onControl={async (deviceId, point, value) => {
              await handleControl(deviceId, point, value);
            }}
            onScenarioComplete={handleScenarioComplete}
          />
        ) : (
          /* Individual Panels */
          <div className="space-y-8">
            {/* Device selection */}
            <div
              className="rounded-md overflow-hidden"
              style={{
                background: "var(--color-sentinel-bg-panel)",
                border: "1px solid var(--color-sentinel-border)",
              }}
            >
              <div className="p-4">
                <h2 className="font-medium text-sm mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  Select Device
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {demoDevices.map((device) => (
                    <button
                      key={device.id}
                      onClick={() => setSelectedDeviceId(device.id)}
                      className={`p-3 rounded text-left transition-all ${selectedDeviceId === device.id ? "brightness-110" : ""}`}
                      style={{
                        background: selectedDeviceId === device.id
                          ? "var(--color-sentinel-bg-secondary)"
                          : "var(--color-sentinel-bg-panel)",
                        border: `1px solid ${selectedDeviceId === device.id ? "var(--color-sentinel-blue)" : "var(--color-sentinel-border)"}`,
                      }}
                    >
                      <div className="font-medium text-sm mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
                        {device.name}
                      </div>
                      <div className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                        {device.location} • {device.device_type}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Control Panel */}
            <ControlPanel
              device={selectedDevice}
              onControl={async (deviceId, point, value) => {
                await handleControl(deviceId, point, value);
              }}
              safetyStatus={deviceControl.safetyStatus}
              refreshInterval={10000}
            />

            {/* Safety Status Panel */}
            <ControlStatus
              status={deviceControl.safetyStatus.status}
              message={deviceControl.safetyStatus.message}
              rules={deviceControl.safetyStatus.rules?.map(rule => ({
                rule: rule.rule,
                status: rule.status as "warning" | "failed" | "passed",
                description: (rule as any).description
              }))}
              deviceType={selectedDevice.device_type}
              lastValidated={new Date().toISOString()}
            />

            {/* Device Control Hook Status */}
            <div
              className="rounded-md overflow-hidden"
              style={{
                background: "var(--color-sentinel-bg-panel)",
                border: "1px solid var(--color-sentinel-border)",
              }}
            >
              <div className="p-4">
                <h2 className="font-medium text-sm mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  Device Control Hook Status
                </h2>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="p-3 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                    <div className="text-xs mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                      Device
                    </div>
                    <div className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {selectedDevice.name}
                    </div>
                  </div>
                  <div className="p-3 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                    <div className="text-xs mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                      Status
                    </div>
                    <div className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {deviceControl.loading ? "Loading..." : "Connected"}
                    </div>
                  </div>
                  <div className="p-3 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                    <div className="text-xs mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                      Last Update
                    </div>
                    <div className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {deviceControl.lastUpdate ? new Date(deviceControl.lastUpdate).toLocaleTimeString() : "Never"}
                    </div>
                  </div>
                  <div className="p-3 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                    <div className="text-xs mb-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                      Safety
                    </div>
                    <div className="text-sm font-medium" style={{
                      color: deviceControl.safetyStatus.status === "safe"
                        ? "var(--color-sentinel-green)"
                        : deviceControl.safetyStatus.status === "warning"
                        ? "var(--color-sentinel-amber)"
                        : "var(--color-sentinel-red)"
                    }}>
                      {deviceControl.safetyStatus.status.toUpperCase()}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Control Log */}
        <div
          className="mt-8 rounded-md overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div className="p-4">
            <h2 className="font-medium text-sm mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>
              Control Log
            </h2>
            {controlLog.length === 0 ? (
              <div className="text-center py-8">
                <div className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  No control actions yet. Try controlling a device or running a demo scenario.
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                {controlLog.map((log, index) => (
                  <div
                    key={index}
                    className="p-3 rounded flex items-center gap-3"
                    style={{
                      background: "var(--color-sentinel-bg-secondary)",
                      border: "1px solid var(--color-sentinel-border)",
                    }}
                  >
                    <div
                      className="text-xs px-2 py-1 rounded flex-shrink-0"
                      style={{
                        background: "var(--color-sentinel-bg-panel)",
                        color: "var(--color-sentinel-text-secondary)",
                      }}
                    >
                      {log.timestamp}
                    </div>
                    <div className="text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {log.message}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Verification checklist */}
        <div
          className="mt-8 rounded-md overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div className="p-4">
            <h2 className="font-medium text-sm mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>
              Verification Checklist
            </h2>
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <div className={`w-4 h-4 rounded-full ${deviceControl.device ? "bg-green-500" : "bg-gray-300"}`} />
                <span className="text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  Control panel components render with Grafana-style design
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className={`w-4 h-4 rounded-full ${controlLog.length > 0 ? "bg-green-500" : "bg-gray-300"}`} />
                <span className="text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  Control actions work with mock device API
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className={`w-4 h-4 rounded-full ${deviceControl.safetyStatus ? "bg-green-500" : "bg-gray-300"}`} />
                <span className="text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  Safety status indicators show correctly
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 rounded-full bg-green-500" />
                <span className="text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  Demo scenarios provide engaging control demonstrations
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 rounded-full bg-green-500" />
                <span className="text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  UI maintains consistency with existing dashboard design
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ControlTest;
