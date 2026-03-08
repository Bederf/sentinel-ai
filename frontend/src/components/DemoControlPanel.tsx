/**
 * DemoControlPanel Component - SENTINEL enhanced control panel for demo scenarios
 *
 * Features:
 * - Pre-configured demo devices and scenarios
 * - Quick control buttons for demo flow
 * - Scenario selection and narrative display
 * - Visual polish with animations
 * - Mobile-optimized layout
 *
 * Follows SENTINEL dark theme design.
 */

import { useState, useEffect } from "react";
import {
  Play,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Zap,
  Thermometer,
  Sun,
  Shield,
  ChevronRight,
  Clock,
  User,
} from "lucide-react";
import { ControlPanel } from "./ControlPanel";
import { ControlStatus } from "./ControlStatus";
import { demoDevices, demoScenarios, demoSafetyStatuses, demoNarratives, quickControls } from "../data/demoControls";
import type { Device } from '@/lib/api';

interface DemoControlPanelProps {
  onControl?: (deviceId: string, point: string, value: number | boolean) => Promise<void>;
  onScenarioComplete?: (scenarioId: string) => void;
}

export function DemoControlPanel({
  onControl,
  onScenarioComplete,
}: DemoControlPanelProps) {
  const [selectedDevice, setSelectedDevice] = useState<Device>(demoDevices[0]);
  const [selectedScenario, setSelectedScenario] = useState(demoScenarios[0]);
  const [activeScenario, setActiveScenario] = useState<string | null>(null);
  const [scenarioStep, setScenarioStep] = useState(0);
  const [isRunning, setIsRunning] = useState(false);
  const [completedScenarios, setCompletedScenarios] = useState<string[]>([]);
  const [showNarrative, setShowNarrative] = useState(true);

  // Get safety status for current device and scenario
  const getSafetyStatus = () => {
    const deviceSafety = demoSafetyStatuses[selectedDevice.id];
    if (!deviceSafety) return { status: "safe" as const };

    const scenarioSafety = selectedScenario.safetyStatus;
    return deviceSafety[scenarioSafety] || deviceSafety.safe || { status: "safe" as const };
  };

  // Get narrative for current device and scenario
  const getNarrative = () => {
    const deviceNarratives = demoNarratives[selectedDevice.id as keyof typeof demoNarratives];
    if (!deviceNarratives) return selectedScenario.narrative;

    const scenarioNarrative = deviceNarratives[selectedScenario.safetyStatus as keyof typeof deviceNarratives];
    return scenarioNarrative || selectedScenario.narrative;
  };

  // Handle device selection
  const handleDeviceSelect = (device: Device) => {
    setSelectedDevice(device);
    setScenarioStep(0);
    setIsRunning(false);
    setActiveScenario(null);

    // Find a scenario for this device
    const deviceScenario = demoScenarios.find(s => s.deviceId === device.id);
    if (deviceScenario) {
      setSelectedScenario(deviceScenario);
    }
  };

  // Handle scenario selection
  const handleScenarioSelect = (scenario: typeof demoScenarios[0]) => {
    setSelectedScenario(scenario);
    setScenarioStep(0);
    setIsRunning(false);
    setActiveScenario(null);

    // Find the device for this scenario
    const device = demoDevices.find(d => d.id === scenario.deviceId);
    if (device) {
      setSelectedDevice(device);
    }
  };

  // Start scenario
  const startScenario = () => {
    setIsRunning(true);
    setActiveScenario(selectedScenario.id);
    setScenarioStep(0);
    setShowNarrative(true);
  };

  // Execute scenario step
  const executeStep = async () => {
    if (!selectedScenario.initialActions || scenarioStep >= selectedScenario.initialActions.length) {
      // Scenario complete
      setIsRunning(false);
      setCompletedScenarios(prev => [...prev, selectedScenario.id]);
      onScenarioComplete?.(selectedScenario.id);
      return;
    }

    const action = selectedScenario.initialActions[scenarioStep];
    try {
      if (onControl) {
        await onControl(selectedDevice.id, action.point, action.value);
      }
      setScenarioStep(prev => prev + 1);
    } catch (err) {
      console.error("Scenario step failed:", err);
    }
  };

  // Handle quick control
  const handleQuickControl = async (control: typeof quickControls[0]) => {
    try {
      if (onControl) {
        await onControl(control.deviceId, control.point, control.value);
      }
    } catch (err) {
      console.error("Quick control failed:", err);
    }
  };

  // Auto-advance scenario steps
  useEffect(() => {
    if (isRunning && activeScenario === selectedScenario.id) {
      const timer = setTimeout(() => {
        executeStep();
      }, 2000); // 2 seconds between steps for demo pacing

      return () => clearTimeout(timer);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isRunning, activeScenario, selectedScenario.id, scenarioStep]);

  const safetyStatus = getSafetyStatus();
  const narrative = getNarrative();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2
            className="text-lg font-medium mb-1"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            Control Panel Demo
          </h2>
          <p
            className="text-sm"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            Interactive demonstration of SENTINEL control capabilities with safety integration
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div
            className="px-3 py-1 rounded text-xs font-medium"
            style={{
              background: "rgba(59, 130, 246, 0.15)",
              color: "var(--color-sentinel-blue)",
            }}
          >
            {completedScenarios.length} / {demoScenarios.length} scenarios
          </div>
          <button
            onClick={() => setCompletedScenarios([])}
            className="flex items-center gap-1 px-3 py-1 rounded text-xs transition-colors"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              color: "var(--color-sentinel-text-secondary)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <RefreshCw className="h-3 w-3" />
            Reset
          </button>
        </div>
      </div>

      {/* Main content grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column: Device and scenario selection */}
        <div className="lg:col-span-1 space-y-6">
          {/* Device selection */}
          <div
            className="rounded-md overflow-hidden"
            style={{
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <div
              className="p-4"
              style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
            >
              <h3
                className="font-medium text-sm mb-3"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Demo Devices
              </h3>
              <div className="space-y-2">
                {demoDevices.map((device) => (
                  <button
                    key={device.id}
                    onClick={() => handleDeviceSelect(device)}
                    className={`w-full flex items-center gap-3 p-3 rounded transition-all ${selectedDevice.id === device.id ? "brightness-110" : ""}`}
                    style={{
                      background:
                        selectedDevice.id === device.id
                          ? "var(--color-sentinel-bg-secondary)"
                          : "transparent",
                      border: `1px solid ${selectedDevice.id === device.id ? "var(--color-sentinel-blue)" : "var(--color-sentinel-border)"}`,
                    }}
                  >
                    <div
                      className="p-2 rounded"
                      style={{
                        background: "rgba(59, 130, 246, 0.15)",
                        color: "var(--color-sentinel-blue)",
                      }}
                    >
                      {device.device_type === "hvac" ? (
                        <Thermometer className="h-4 w-4" />
                      ) : device.device_type === "lighting" ? (
                        <Sun className="h-4 w-4" />
                      ) : (
                        <Shield className="h-4 w-4" />
                      )}
                    </div>
                    <div className="flex-1 text-left">
                      <div
                        className="font-medium text-sm"
                        style={{ color: "var(--color-sentinel-text-primary)" }}
                      >
                        {device.name}
                      </div>
                      <div
                        className="text-xs"
                        style={{ color: "var(--color-sentinel-text-secondary)" }}
                      >
                        {device.location}
                      </div>
                    </div>
                    {selectedDevice.id === device.id && (
                      <ChevronRight className="h-4 w-4" style={{ color: "var(--color-sentinel-blue)" }} />
                    )}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Scenario selection */}
          <div
            className="rounded-md overflow-hidden"
            style={{
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <div
              className="p-4"
              style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
            >
              <h3
                className="font-medium text-sm mb-3"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Demo Scenarios
              </h3>
              <div className="space-y-2">
                {demoScenarios.map((scenario) => {
                  const isCompleted = completedScenarios.includes(scenario.id);
                  // const _isActive = activeScenario === scenario.id; // Reserved for future use
                  const isSelected = selectedScenario.id === scenario.id;

                  return (
                    <button
                      key={scenario.id}
                      onClick={() => handleScenarioSelect(scenario)}
                      className={`w-full flex items-center gap-3 p-3 rounded transition-all ${isSelected ? "brightness-110" : ""}`}
                      style={{
                        background: isSelected
                          ? "var(--color-sentinel-bg-secondary)"
                          : "transparent",
                        border: `1px solid ${isSelected ? getScenarioColor(scenario.safetyStatus) : "var(--color-sentinel-border)"}`,
                      }}
                    >
                      <div
                        className="p-2 rounded"
                        style={{
                          background: `${getScenarioColor(scenario.safetyStatus)}20`,
                          color: getScenarioColor(scenario.safetyStatus),
                        }}
                      >
                        {scenario.safetyStatus === "safe" ? (
                          <CheckCircle className="h-4 w-4" />
                        ) : scenario.safetyStatus === "warning" ? (
                          <AlertTriangle className="h-4 w-4" />
                        ) : (
                          <XCircle className="h-4 w-4" />
                        )}
                      </div>
                      <div className="flex-1 text-left">
                        <div className="flex items-center justify-between">
                          <div
                            className="font-medium text-sm"
                            style={{ color: "var(--color-sentinel-text-primary)" }}
                          >
                            {scenario.name}
                          </div>
                          {isCompleted && (
                            <CheckCircle className="h-3 w-3" style={{ color: "var(--color-sentinel-green)" }} />
                          )}
                        </div>
                        <div
                          className="text-xs"
                          style={{ color: "var(--color-sentinel-text-secondary)" }}
                        >
                          {scenario.description}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Scenario controls */}
            <div className="p-4">
              <div className="flex items-center gap-2 mb-4">
                <button
                  onClick={startScenario}
                  disabled={isRunning}
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded font-medium transition-colors"
                  style={{
                    background: isRunning
                      ? "var(--color-sentinel-bg-secondary)"
                      : "var(--color-sentinel-amber)",
                    color: isRunning
                      ? "var(--color-sentinel-text-disabled)"
                      : "white",
                    cursor: isRunning ? "not-allowed" : "pointer",
                  }}
                >
                  <Play className="h-4 w-4" />
                  {isRunning ? "Running..." : "Run Scenario"}
                </button>
              </div>

              {/* Scenario progress */}
              {isRunning && activeScenario === selectedScenario.id && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      Step {scenarioStep + 1} of {selectedScenario.initialActions?.length || 1}
                    </span>
                    <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      {Math.round(((scenarioStep + 1) / (selectedScenario.initialActions?.length || 1)) * 100)}%
                    </span>
                  </div>
                  <div
                    className="h-2 rounded-full overflow-hidden"
                    style={{ background: "var(--color-sentinel-border)" }}
                  >
                    <div
                      className="h-full rounded-full transition-all duration-300"
                      style={{
                        width: `${((scenarioStep + 1) / (selectedScenario.initialActions?.length || 1)) * 100}%`,
                        background: getScenarioColor(selectedScenario.safetyStatus),
                      }}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Quick controls */}
          <div
            className="rounded-md overflow-hidden"
            style={{
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <div className="p-4">
              <h3
                className="font-medium text-sm mb-3"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Quick Controls
              </h3>
              <div className="grid grid-cols-2 gap-2">
                {quickControls
                  .filter(control => control.deviceId === selectedDevice.id)
                  .slice(0, 4)
                  .map((control, index) => (
                    <button
                      key={index}
                      onClick={() => handleQuickControl(control)}
                      className="p-2 rounded text-xs text-left transition-colors hover:brightness-110"
                      style={{
                        background: "var(--color-sentinel-bg-secondary)",
                        border: "1px solid var(--color-sentinel-border)",
                      }}
                    >
                      <div className="flex items-center gap-1 mb-1">
                        <Zap className="h-3 w-3" style={{ color: "var(--color-sentinel-amber)" }} />
                        <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                          {control.label}
                        </span>
                      </div>
                      <div style={{ color: "var(--color-sentinel-text-secondary)" }}>
                        {control.description}
                      </div>
                    </button>
                  ))}
              </div>
            </div>
          </div>
        </div>

        {/* Right column: Control panel and narrative */}
        <div className="lg:col-span-2 space-y-6">
          {/* Narrative panel */}
          {showNarrative && (
            <div
              className="rounded-md overflow-hidden"
              style={{
                background: "var(--color-sentinel-bg-panel)",
                border: "1px solid var(--color-sentinel-border)",
              }}
            >
              <div
                className="p-4 flex items-center justify-between"
                style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
              >
                <div className="flex items-center gap-2">
                  <User className="h-4 w-4" style={{ color: "var(--color-sentinel-blue)" }} />
                  <h3
                    className="font-medium text-sm"
                    style={{ color: "var(--color-sentinel-text-primary)" }}
                  >
                    Demo Narrative
                  </h3>
                </div>
                <button
                  onClick={() => setShowNarrative(false)}
                  className="text-xs px-2 py-1 rounded transition-colors"
                  style={{
                    background: "var(--color-sentinel-bg-secondary)",
                    color: "var(--color-sentinel-text-secondary)",
                  }}
                >
                  Hide
                </button>
              </div>
              <div className="p-4">
                <div className="flex items-start gap-3">
                  <div
                    className="p-2 rounded flex-shrink-0"
                    style={{
                      background: "rgba(245, 158, 11, 0.15)",
                      color: "var(--color-sentinel-amber)",
                    }}
                  >
                    <Clock className="h-4 w-4" />
                  </div>
                  <div>
                    <p
                      className="text-sm mb-2"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      {narrative}
                    </p>
                    <div className="flex items-center gap-2">
                      <span
                        className="text-xs px-2 py-1 rounded"
                        style={{
                          background: "var(--color-sentinel-bg-secondary)",
                          color: "var(--color-sentinel-text-secondary)",
                        }}
                      >
                        Role: FM Operator
                      </span>
                      <span
                        className="text-xs px-2 py-1 rounded"
                        style={{
                          background: "var(--color-sentinel-bg-secondary)",
                          color: "var(--color-sentinel-text-secondary)",
                        }}
                      >
                        Goal: {selectedScenario.expectedOutcome}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Control panel */}
          <ControlPanel
            device={selectedDevice}
            onControl={onControl}
            safetyStatus={safetyStatus}
            refreshInterval={10000}
          />

          {/* Safety status panel */}
          <ControlStatus
            status={safetyStatus.status}
            message={safetyStatus.message}
            rules={safetyStatus.rules}
            deviceType={selectedDevice.device_type}
            lastValidated={new Date().toISOString()}
          />

          {/* Expected outcome */}
          <div
            className="rounded-md overflow-hidden"
            style={{
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <div
              className="p-4"
              style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
            >
              <h3
                className="font-medium text-sm mb-2"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Expected Outcome
              </h3>
              <p
                className="text-sm"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                {selectedScenario.expectedOutcome}
              </p>
            </div>
            <div className="p-4">
              <div className="flex items-center gap-2">
                {selectedScenario.safetyStatus === "safe" && (
                  <div className="flex items-center gap-1">
                    <CheckCircle className="h-4 w-4" style={{ color: "var(--color-sentinel-green)" }} />
                    <span
                      className="text-xs"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      Safe operation permitted
                    </span>
                  </div>
                )}
                {selectedScenario.safetyStatus === "warning" && (
                  <div className="flex items-center gap-1">
                    <AlertTriangle className="h-4 w-4" style={{ color: "var(--color-sentinel-amber)" }} />
                    <span
                      className="text-xs"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      Warning issued with audit trail
                    </span>
                  </div>
                )}
                {selectedScenario.safetyStatus === "blocked" && (
                  <div className="flex items-center gap-1">
                    <XCircle className="h-4 w-4" style={{ color: "var(--color-sentinel-red)" }} />
                    <span
                      className="text-xs"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      Action blocked for safety
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Helper function to get scenario color
function getScenarioColor(safetyStatus: string): string {
  switch (safetyStatus) {
    case "safe":
      return "var(--color-sentinel-green)";
    case "warning":
      return "var(--color-sentinel-amber)";
    case "blocked":
      return "var(--color-sentinel-red)";
    default:
      return "var(--color-sentinel-text-secondary)";
  }
}

export default DemoControlPanel;
