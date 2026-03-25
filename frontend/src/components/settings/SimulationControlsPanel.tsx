import { memo, useCallback, useEffect, useState, type ReactNode } from "react";
import { Gauge, Play, Square } from "lucide-react";
import { useSimulation } from "../../contexts/SimulationContext";
import {
  changeSimulationSpeed,
  getSimulationStopped,
  setSimulationStopped,
  startSimulation,
  stopSimulation,
} from "../../lib/simulationApi";

const SPEED_PRESETS = [1, 5, 10, 50, 100] as const;

interface SimulationControlsPanelProps {
  readOnly: boolean;
  selectedSiteId: string | null;
  onError?: (msg: string) => void;
}

interface SimulationPanelActions {
  changingSpeed: boolean;
  handleSpeedChange: (speed: number) => Promise<void>;
  handleStart: () => Promise<void>;
  handleStop: () => Promise<void>;
  persistentStopped: boolean;
  starting: boolean;
  stopping: boolean;
}

function usePersistentSimulationStopFlag() {
  const [persistentStopped, setPersistentStopped] = useState(false);

  useEffect(() => {
    getSimulationStopped()
      .then((data) => setPersistentStopped(!!data.stopped))
      .catch(() => {});
  }, []);

  return { persistentStopped, setPersistentStopped };
}

function speedToSlider(speed: number): number {
  return Math.round((Math.log10(Math.max(0.1, speed)) + 1) * 25);
}

function sliderToSpeed(value: number): number {
  return Math.round(10 ** (value / 25 - 1) * 10) / 10;
}

function useSimulationPanelActions(
  readOnly: boolean,
  selectedSiteId: string | null,
  onError?: (msg: string) => void
): SimulationPanelActions {
  const sim = useSimulation();
  const [changingSpeed, setChangingSpeed] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [starting, setStarting] = useState(false);
  const { persistentStopped, setPersistentStopped } = usePersistentSimulationStopFlag();

  const handleSpeedChange = useCallback(async (speed: number) => {
    if (readOnly || changingSpeed) return;
    setChangingSpeed(true);
    try {
      await changeSimulationSpeed(speed);
      await sim.refresh();
    } catch (error) {
      onError?.(error instanceof Error ? error.message : "Failed to change speed");
    } finally {
      setChangingSpeed(false);
    }
  }, [changingSpeed, onError, readOnly, sim]);

  const handleStop = useCallback(async () => {
    if (readOnly || stopping) return;
    setStopping(true);
    try {
      if (sim.running) {
        await stopSimulation();
      }
      await setSimulationStopped(true);
      setPersistentStopped(true);
      await sim.refresh();
    } catch (error) {
      onError?.(error instanceof Error ? error.message : "Failed to stop simulation");
    } finally {
      setStopping(false);
    }
  }, [onError, readOnly, setPersistentStopped, sim, stopping]);

  const handleStart = useCallback(async () => {
    if (readOnly || starting) return;
    if (!selectedSiteId) {
      onError?.("Select a site before starting the simulation.");
      return;
    }
    setStarting(true);
    try {
      await setSimulationStopped(false);
      setPersistentStopped(false);
      await startSimulation({
        scenario: "sentinel_annual",
        duration_minutes: 3650,
        site_id: selectedSiteId,
      });
      await sim.refresh();
    } catch (error) {
      onError?.(error instanceof Error ? error.message : "Failed to start simulation");
    } finally {
      setStarting(false);
    }
  }, [onError, readOnly, selectedSiteId, setPersistentStopped, sim, starting]);

  return {
    changingSpeed,
    handleSpeedChange,
    handleStart,
    handleStop,
    persistentStopped,
    starting,
    stopping,
  };
}

function SimulationPanelHeader() {
  return (
    <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
      <div className="flex items-center gap-3">
        <div
          className="p-2 rounded"
          style={{
            background: "rgba(59, 130, 246, 0.15)",
            color: "var(--color-sentinel-blue)",
          }}
        >
          <Gauge className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Simulation Controls
          </h2>
          <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Adjust simulation speed and view progress
          </p>
        </div>
      </div>
    </div>
  );
}

function SimulationActionButton({
  children,
  disabled,
  kind,
  onClick,
}: {
  children: ReactNode;
  disabled: boolean;
  kind: "start" | "stop";
  onClick: () => void;
}) {
  const tone = kind === "start"
    ? {
        background: "rgba(16, 185, 129, 0.15)",
        color: "var(--color-sentinel-green)",
        border: "1px solid rgba(16, 185, 129, 0.3)",
      }
    : {
        background: "rgba(220, 38, 38, 0.15)",
        color: "var(--color-sentinel-red)",
        border: "1px solid rgba(220, 38, 38, 0.3)",
      };

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center gap-2 px-4 py-2 rounded text-sm font-medium transition-colors hover:brightness-110"
      style={{
        ...tone,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.6 : 1,
      }}
      type="button"
    >
      {children}
    </button>
  );
}

function SimulationInactiveState({
  persistentStopped,
  readOnly,
  starting,
  onStart,
}: {
  persistentStopped: boolean;
  readOnly: boolean;
  starting: boolean;
  onStart: () => void;
}) {
  return (
    <div
      className="rounded-lg p-4 text-center space-y-3"
      style={{
        background: "var(--color-sentinel-bg-secondary)",
        border: "1px solid var(--glass-border)",
      }}
    >
      <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
        {persistentStopped ? "Simulation stopped. Will not auto-start on restart." : "No simulation running"}
      </p>
      <SimulationActionButton disabled={readOnly || starting} kind="start" onClick={onStart}>
        <Play className="h-4 w-4" />
        {starting ? "Starting..." : "Start Simulation"}
      </SimulationActionButton>
    </div>
  );
}

function SimulationMetricCard({
  children,
  label,
}: {
  children: ReactNode;
  label: string;
}) {
  return (
    <div
      className="flex-1 rounded-lg p-3"
      style={{
        background: "var(--color-sentinel-bg-secondary)",
        border: "1px solid var(--glass-border)",
      }}
    >
      <p className="text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
        {label}
      </p>
      {children}
    </div>
  );
}

function SimulationMetrics({ sim }: { sim: ReturnType<typeof useSimulation> }) {
  return (
    <div className="flex flex-col sm:flex-row gap-4">
      <SimulationMetricCard label="Current Speed">
        <p className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
          {sim.speedMultiplier}x
          <span className="text-sm font-normal ml-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            {sim.secondsPerHour.toFixed(1)}s per simulated hour
          </span>
        </p>
      </SimulationMetricCard>
      <SimulationMetricCard label="Progress">
        <p className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
          Day {sim.daysSimulated} of 365
          <span className="text-sm font-normal ml-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            {sim.progressPct}%
          </span>
        </p>
        <div className="mt-2 h-1.5 rounded-full overflow-hidden" style={{ background: "var(--color-sentinel-bg-hover)" }}>
          <div
            className="h-full rounded-full transition-all"
            style={{ width: `${sim.progressPct}%`, background: "var(--color-sentinel-blue)" }}
          />
        </div>
      </SimulationMetricCard>
      <SimulationMetricCard label="Energy Consumed">
        <p className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
          {sim.totalEnergyKwh >= 1000
            ? `${(sim.totalEnergyKwh / 1000).toFixed(1)} MWh`
            : `${Math.round(sim.totalEnergyKwh)} kWh`}
          <span className="text-sm font-normal ml-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            {sim.currentHourPowerKw > 0 ? `${sim.currentHourPowerKw.toFixed(1)} kW now` : ""}
          </span>
        </p>
      </SimulationMetricCard>
    </div>
  );
}

function SimulationSpeedPresets({
  changingSpeed,
  onSelect,
  readOnly,
  speedMultiplier,
}: {
  changingSpeed: boolean;
  onSelect: (speed: number) => void;
  readOnly: boolean;
  speedMultiplier: number;
}) {
  return (
    <div>
      <label className="block text-sm font-medium mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
        Speed Presets
      </label>
      <div className="flex flex-wrap gap-2">
        {SPEED_PRESETS.map((speed) => {
          const isActive = speedMultiplier === speed;
          return (
            <button
              key={speed}
              onClick={() => onSelect(speed)}
              disabled={readOnly || changingSpeed}
              className="px-4 py-2 text-sm rounded font-medium transition-colors"
              style={{
                background: isActive ? "rgba(59, 130, 246, 0.25)" : "var(--color-sentinel-bg-secondary)",
                color: isActive ? "var(--color-sentinel-blue)" : "var(--color-sentinel-text-primary)",
                border: `1px solid ${isActive ? "rgba(59, 130, 246, 0.4)" : "var(--glass-border)"}`,
                cursor: readOnly || changingSpeed ? "not-allowed" : "pointer",
                opacity: readOnly ? 0.6 : 1,
              }}
              type="button"
            >
              {speed}x
            </button>
          );
        })}
      </div>
    </div>
  );
}

function SimulationFineControl({
  changingSpeed,
  onSelect,
  readOnly,
  speedMultiplier,
}: {
  changingSpeed: boolean;
  onSelect: (speed: number) => void;
  readOnly: boolean;
  speedMultiplier: number;
}) {
  const sliderValue = speedToSlider(speedMultiplier);

  return (
    <div>
      <div className="flex justify-between mb-2">
        <label className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
          Fine Control
        </label>
        <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          {speedMultiplier}x
        </span>
      </div>
      <input
        type="range"
        min="0"
        max="100"
        value={sliderValue}
        onChange={(event) => onSelect(sliderToSpeed(Number.parseInt(event.target.value, 10)))}
        disabled={readOnly || changingSpeed}
        className="w-full h-3"
        style={{ cursor: readOnly ? "not-allowed" : "pointer" }}
        aria-label="Simulation speed"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={sliderValue}
      />
      <div className="flex justify-between text-xs mt-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>
        <span>0.1x</span>
        <span>1x</span>
        <span>10x</span>
        <span>100x</span>
        <span>1000x</span>
      </div>
    </div>
  );
}

function SimulationRunningState({
  actions,
  readOnly,
  sim,
}: {
  actions: SimulationPanelActions;
  readOnly: boolean;
  sim: ReturnType<typeof useSimulation>;
}) {
  return (
    <div className="space-y-5">
      <SimulationMetrics sim={sim} />

      <div>
        <SimulationActionButton disabled={readOnly || actions.stopping} kind="stop" onClick={() => void actions.handleStop()}>
          <Square className="h-4 w-4" />
          {actions.stopping ? "Stopping..." : "Stop Simulation"}
        </SimulationActionButton>
      </div>

      <SimulationSpeedPresets
        changingSpeed={actions.changingSpeed}
        onSelect={(speed) => void actions.handleSpeedChange(speed)}
        readOnly={readOnly}
        speedMultiplier={sim.speedMultiplier}
      />

      <SimulationFineControl
        changingSpeed={actions.changingSpeed}
        onSelect={(speed) => void actions.handleSpeedChange(speed)}
        readOnly={readOnly}
        speedMultiplier={sim.speedMultiplier}
      />
    </div>
  );
}

export const SimulationControlsPanel = memo(function SimulationControlsPanel({
  readOnly,
  selectedSiteId,
  onError,
}: SimulationControlsPanelProps) {
  const sim = useSimulation();
  const actions = useSimulationPanelActions(readOnly, selectedSiteId, onError);

  return (
    <div className="glass-panel overflow-hidden">
      <SimulationPanelHeader />
      <div className="p-6">
        {!sim.running ? (
          <SimulationInactiveState
            persistentStopped={actions.persistentStopped}
            readOnly={readOnly}
            starting={actions.starting}
            onStart={() => void actions.handleStart()}
          />
        ) : (
          <SimulationRunningState actions={actions} readOnly={readOnly} sim={sim} />
        )}
      </div>
    </div>
  );
});
