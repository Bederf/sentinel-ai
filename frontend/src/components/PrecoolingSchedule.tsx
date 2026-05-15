import { useState } from "react";

import { Clock, Thermometer, Zap, CheckCircle, AlertTriangle, Play } from "lucide-react";

interface ScheduleSegment {
  type: "precooling" | "load_shedding" | "recovery";
  start: string;
  end: string;
  label: string;
  color: string;
  actions: Array<{
    time: string;
    action: string;
    value: string;
    description: string;
  }>;
}

interface ActionMarker {
  time: string;
  label: string;
  icon: React.ReactNode;
  color: string;
  details: string;
}

interface ReadinessCheck {
  check: string;
  status: string;
  time: string;
  passed: boolean;
}

interface PrecoolingScheduleProps {
  schedule: ScheduleSegment[];
  currentTime: string;
  readinessChecks: ReadinessCheck[];
  onSegmentClick?: (segment: ScheduleSegment) => void;
  onActionClick?: (action: ActionMarker) => void;
}

function timeToMinutes(time: string): number {
  const [hours, minutes] = time.split(":").map(Number);
  return hours * 60 + minutes;
}

function getSegmentColor(type: ScheduleSegment["type"]): { bg: string; border: string; text: string } {
  switch (type) {
    case "precooling":
      return {
        bg: "bg-blue-900/20",
        border: "border-blue-500/50",
        text: "text-blue-300"
      };
    case "load_shedding":
      return {
        bg: "bg-red-900/20",
        border: "border-red-500/50",
        text: "text-red-300"
      };
    case "recovery":
      return {
        bg: "bg-green-900/20",
        border: "border-green-500/50",
        text: "text-green-300"
      };
  }
}

function getActionIcon(action: string): React.ReactNode {
  switch (action.toLowerCase()) {
    case "chw":
    case "chilled water":
      return <Thermometer className="h-4 w-4" />;
    case "ahu":
    case "fan speed":
      return <Zap className="h-4 w-4" />;
    case "ventilation":
      return <Play className="h-4 w-4" />;
    case "temperature":
      return <Thermometer className="h-4 w-4" />;
    default:
      return <Clock className="h-4 w-4" />;
  }
}

function badgeSpan(variant: "blue" | "red" | "green" | "gray" | "emerald", size: "xs" | "sm" | "lg" = "xs", children: React.ReactNode) {
  const colorMap: Record<string, { bg: string; color: string }> = {
    blue: { bg: "rgba(59,130,246,0.15)", color: "var(--color-sentinel-blue)" },
    red: { bg: "rgba(220,38,38,0.15)", color: "var(--color-sentinel-red)" },
    green: { bg: "rgba(16,185,129,0.15)", color: "var(--color-sentinel-green)" },
    emerald: { bg: "rgba(16,185,129,0.15)", color: "var(--color-sentinel-green)" },
    gray: { bg: "rgba(142,142,142,0.15)", color: "var(--color-sentinel-text-secondary)" },
  };
  const sizeClass = size === "lg" ? "px-3 py-1 text-sm" : size === "sm" ? "px-2 py-0.5 text-xs" : "px-1.5 py-0.5 text-xs";
  return (
    <span className={`inline-flex items-center font-medium rounded-full ${sizeClass}`} style={colorMap[variant] || colorMap.gray}>
      {children}
    </span>
  );
}

export function PrecoolingSchedule({
  schedule,
  currentTime,
  readinessChecks,
  onSegmentClick,
  onActionClick
}: PrecoolingScheduleProps) {
  const [hoveredAction, setHoveredAction] = useState<string | null>(null);
  const [selectedSegment, setSelectedSegment] = useState<string | null>(null);

  const timelineStart = Math.min(...schedule.map(s => timeToMinutes(s.start)));
  const timelineEnd = Math.max(...schedule.map(s => timeToMinutes(s.end)));
  const timelineDuration = timelineEnd - timelineStart;
  const currentMinutes = timeToMinutes(currentTime);

  const isCurrentTimeInTimeline = currentMinutes >= timelineStart && currentMinutes <= timelineEnd;

  const allActions = schedule.flatMap(segment =>
    segment.actions.map(action => ({
      ...action,
      segmentType: segment.type,
      segmentLabel: segment.label
    }))
  );

  const futureActions = allActions.filter(action => timeToMinutes(action.time) > currentMinutes);
  const nextAction = futureActions.length > 0 ? futureActions[0] : null;
  const countdownMinutes = nextAction ? timeToMinutes(nextAction.time) - currentMinutes : 0;

  const handleSegmentClick = (segment: ScheduleSegment) => {
    setSelectedSegment(segment.label);
    onSegmentClick?.(segment);
  };

  const handleActionHover = (actionTime: string) => {
    setHoveredAction(actionTime);
  };

  function getPositionPercent(time: string): number {
    const minutes = timeToMinutes(time);
    return ((minutes - timelineStart) / timelineDuration) * 100;
  }

  function getSegmentWidth(start: string, end: string): number {
    const startMinutes = timeToMinutes(start);
    const endMinutes = timeToMinutes(end);
    return ((endMinutes - startMinutes) / timelineDuration) * 100;
  }

  return (
    <div
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
        borderRadius: 8,
        padding: 16,
      }}
    >
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Pre-cooling Schedule Timeline</h3>
          <p className="text-sm mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Visualization of optimization actions before and during load shedding</p>
        </div>
        {nextAction && (
          <div className="flex items-center gap-2 px-3 py-2 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
            <Clock className="h-4 w-4" style={{ color: "var(--color-sentinel-blue)" }} />
            <div>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Next action in</p>
              <p className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>{countdownMinutes} min</p>
            </div>
          </div>
        )}
      </div>

      <div className="relative mb-8">
        <div className="h-2 rounded-full relative" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
          {isCurrentTimeInTimeline && (
            <div
              className="absolute top-1/2 transform -translate-y-1/2 w-1 h-6 bg-white z-20"
              style={{ left: `${getPositionPercent(currentTime)}%` }}
            >
              <div className="absolute -top-6 left-1/2 transform -translate-x-1/2 whitespace-nowrap">
                {badgeSpan("gray", "xs", "NOW")}
              </div>
            </div>
          )}

          {schedule.map((segment, idx) => {
            const color = getSegmentColor(segment.type);
            const left = getPositionPercent(segment.start);
            const width = getSegmentWidth(segment.start, segment.end);

            return (
              <div
                key={idx}
                className={`absolute top-0 h-2 rounded-full cursor-pointer transition-all hover:opacity-90 ${color.bg} ${color.border} border`}
                style={{ left: `${left}%`, width: `${width}%` }}
                onClick={() => handleSegmentClick(segment)}
                onMouseEnter={() => setHoveredAction(null)}
              >
                <div className="absolute -top-8 left-1/2 transform -translate-x-1/2 whitespace-nowrap">
                  {badgeSpan(segment.type === "precooling" ? "blue" : segment.type === "load_shedding" ? "red" : "green", "xs", segment.label)}
                </div>

                {segment.actions.map((action, actionIdx) => {
                  const actionLeft = getPositionPercent(action.time) - left;
                  const isHovered = hoveredAction === `${segment.label}-${action.time}`;

                  return (
                    <div
                      key={actionIdx}
                      className={`absolute top-1/2 transform -translate-y-1/2 -translate-x-1/2 w-8 h-8 rounded-full border-2 cursor-pointer transition-all hover:scale-110 ${isHovered ? 'ring-2 ring-white ring-opacity-50' : ''}`}
                      style={{
                        left: `${actionLeft}%`,
                        backgroundColor: color.bg.replace("/20", "/40"),
                        borderColor: color.border.replace("/50", "")
                      }}
                      onClick={(e) => {
                        e.stopPropagation();
                        onActionClick?.({
                          time: action.time,
                          label: action.action,
                          icon: getActionIcon(action.action),
                          color: color.border,
                          details: `${action.value}: ${action.description}`
                        });
                      }}
                      onMouseEnter={() => handleActionHover(`${segment.label}-${action.time}`)}
                      onMouseLeave={() => setHoveredAction(null)}
                      title={action.description}
                    >
                      <div className="flex items-center justify-center h-full">
                        {getActionIcon(action.action)}
                      </div>
                      <div className="absolute -bottom-6 left-1/2 transform -translate-x-1/2 whitespace-nowrap">
                        <span className="text-xs font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>{action.time}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            );
          })}

          <div className="absolute -bottom-8 left-0 right-0 flex justify-between">
            {schedule.map((segment, idx) => (
              <div key={idx} className="flex flex-col items-center">
                <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>{segment.start}</span>
                {idx === schedule.length - 1 && (
                  <span className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>{segment.end}</span>
                )}
              </div>
            ))}
          </div>
        </div>

        {selectedSegment && (
          <div className="mt-12 p-4 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>Segment Details</h3>
              {badgeSpan(
                schedule.find(s => s.label === selectedSegment)?.type === "precooling" ? "blue" :
                schedule.find(s => s.label === selectedSegment)?.type === "load_shedding" ? "red" : "green",
                "xs",
                selectedSegment
              )}
            </div>
            {schedule
              .filter(s => s.label === selectedSegment)
              .map((segment, idx) => (
                <div key={idx} className="space-y-3">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <span className="text-sm" style={{ color: "var(--color-sentinel-text-disabled)" }}>Start Time</span>
                      <p className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>{segment.start}</p>
                    </div>
                    <div>
                      <span className="text-sm" style={{ color: "var(--color-sentinel-text-disabled)" }}>End Time</span>
                      <p className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>{segment.end}</p>
                    </div>
                  </div>
                  <div>
                    <span className="text-sm mb-2 block" style={{ color: "var(--color-sentinel-text-disabled)" }}>Actions</span>
                    <div className="space-y-2">
                      {segment.actions.map((action, actionIdx) => (
                        <div key={actionIdx} className="flex items-center gap-3 p-2 rounded" style={{ background: "var(--color-sentinel-bg-panel)" }}>
                          <div className="flex-shrink-0">
                            {getActionIcon(action.action)}
                          </div>
                          <div className="flex-grow">
                            <p className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>{action.action}</p>
                            <p className="text-sm" style={{ color: "var(--color-sentinel-text-disabled)" }}>{action.value}</p>
                          </div>
                          {badgeSpan("gray", "xs", action.time)}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
          </div>
        )}
      </div>

      <div className="border-t pt-6" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <h3 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Generator Readiness Checks</h3>
        <p className="mb-4" style={{ color: "var(--color-sentinel-text-secondary)" }}>System verification before load shedding begins</p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {readinessChecks.map((check, idx) => (
            <div
              key={idx}
              className={`p-4 rounded ${check.passed ? 'border' : 'border'}`}
              style={{
                background: check.passed ? "rgba(16,185,129,0.1)" : "rgba(220,38,38,0.1)",
                borderColor: check.passed ? "rgba(16,185,129,0.3)" : "rgba(220,38,38,0.3)",
              }}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  {check.passed ? (
                    <CheckCircle className="h-5 w-5" style={{ color: "var(--color-sentinel-green)" }} />
                  ) : (
                    <AlertTriangle className="h-5 w-5" style={{ color: "var(--color-sentinel-red)" }} />
                  )}
                  <p className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>{check.check}</p>
                </div>
                {badgeSpan(check.passed ? "emerald" : "red", "xs", check.passed ? "PASSED" : "FAILED")}
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm" style={{ color: "var(--color-sentinel-text-disabled)" }}>Status</span>
                <p className={`font-medium ${check.passed ? '' : ''}`} style={{ color: check.passed ? "var(--color-sentinel-green)" : "var(--color-sentinel-red)" }}>
                  {check.status}
                </p>
              </div>
              <div className="flex items-center justify-between mt-2">
                <span className="text-sm" style={{ color: "var(--color-sentinel-text-disabled)" }}>Time</span>
                <span className="text-sm" style={{ color: "var(--color-sentinel-text-disabled)" }}>{check.time}</span>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-6 p-4 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {readinessChecks.every(c => c.passed) ? (
                <>
                  <CheckCircle className="h-6 w-6" style={{ color: "var(--color-sentinel-green)" }} />
                  <div>
                    <p className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>All checks passed</p>
                    <p className="text-sm" style={{ color: "var(--color-sentinel-text-disabled)" }}>Generator ready for load shedding</p>
                  </div>
                </>
              ) : (
                <>
                  <AlertTriangle className="h-6 w-6" style={{ color: "var(--color-sentinel-red)" }} />
                  <div>
                    <p className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>Checks require attention</p>
                    <p className="text-sm" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                      {readinessChecks.filter(c => !c.passed).length} of {readinessChecks.length} checks failed
                    </p>
                  </div>
                </>
              )}
            </div>
            {badgeSpan(readinessChecks.every(c => c.passed) ? "emerald" : "red", "lg", readinessChecks.every(c => c.passed) ? "READY" : "NOT READY")}
          </div>
        </div>
      </div>

      <div className="mt-6 pt-6 border-t" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <span className="text-sm font-medium mb-3 block" style={{ color: "var(--color-sentinel-text-primary)" }}>Timeline Legend</span>
        <div className="flex flex-wrap gap-4">
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded bg-blue-900/20 border border-blue-500/50"></div>
            <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Pre-cooling phase</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded bg-red-900/20 border border-red-500/50"></div>
            <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Load shedding phase</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded bg-green-900/20 border border-green-500/50"></div>
            <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Recovery phase</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-full border-2 border-blue-400"></div>
            <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Action marker (click for details)</span>
          </div>
        </div>
      </div>
    </div>
  );
}

PrecoolingSchedule.defaultProps = {
  schedule: [
    {
      type: "precooling" as const,
      start: "14:45",
      end: "16:00",
      label: "PRE-COOLING",
      color: "blue",
      actions: [
        {
          time: "14:45",
          action: "CHW setpoint",
          value: "6°C → 5°C",
          description: "Chilled water setpoint adjustment for maximum cooling"
        },
        {
          time: "14:50",
          action: "AHU fan speed",
          value: "70% → 90%",
          description: "Air handling unit fan speed increase"
        },
        {
          time: "15:00",
          action: "Ventilation mode",
          value: "Ventilation only",
          description: "Switch to ventilation only mode for free cooling"
        },
        {
          time: "15:15",
          action: "Temperature check",
          value: "20.5°C",
          description: "Verify target pre-cooling temperature achieved"
        }
      ]
    },
    {
      type: "load_shedding" as const,
      start: "16:00",
      end: "18:30",
      label: "LOAD SHEDDING",
      color: "red",
      actions: [
        {
          time: "16:00",
          action: "Power loss",
          value: "Grid offline",
          description: "Load shedding begins, building on generator power"
        },
        {
          time: "16:30",
          action: "Controlled drift",
          value: "22°C → 25°C",
          description: "Allow controlled temperature drift within comfort limits"
        },
        {
          time: "17:30",
          action: "Monitor",
          value: "24.8°C",
          description: "Check temperature against comfort limit (26°C)"
        }
      ]
    },
    {
      type: "recovery" as const,
      start: "18:30",
      end: "19:30",
      label: "RECOVERY",
      color: "green",
      actions: [
        {
          time: "18:30",
          action: "Power restored",
          value: "Grid online",
          description: "Grid power restored, begin staged restart"
        },
        {
          time: "18:45",
          action: "Chiller restart",
          value: "Staged sequence",
          description: "Gradual restart of chilled water systems"
        },
        {
          time: "19:15",
          action: "Temperature recovery",
          value: "25°C → 22°C",
          description: "Return to normal operating temperature"
        }
      ]
    }
  ],
  currentTime: "15:30",
  readinessChecks: [
    {
      check: "Generator test",
      status: "PASSED",
      time: "13:45",
      passed: true
    },
    {
      check: "UPS status",
      status: "96% capacity",
      time: "Current",
      passed: true
    },
    {
      check: "Fuel level",
      status: "78%",
      time: "Current",
      passed: true
    }
  ]
};
