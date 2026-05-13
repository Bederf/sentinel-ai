/**
 * PrecoolingSchedule Component - Timeline visualization of pre-cooling actions
 *
 * Shows a horizontal timeline from current time to end of outage with:
 * - Color-coded segments: PRE-COOLING (blue), LOAD SHEDDING (red), RECOVERY (green)
 * - Action markers within segments with tooltips
 * - Status indicators for generator readiness checks
 * - Interactive click and hover features
 *
 * Follows SENTINEL dark theme design.
 */

import { useState } from "react";

import { Clock, Thermometer, Zap, CheckCircle, AlertTriangle, Play } from "lucide-react";

interface ScheduleSegment {
  type: "precooling" | "load_shedding" | "recovery";
  start: string; // HH:MM format
  end: string;   // HH:MM format
  label: string;
  color: string;
  actions: Array<{
    time: string; // HH:MM format
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
  currentTime: string; // HH:MM format
  readinessChecks: ReadinessCheck[];
  onSegmentClick?: (segment: ScheduleSegment) => void;
  onActionClick?: (action: ActionMarker) => void;
}

// Convert time string to minutes since midnight
function timeToMinutes(time: string): number {
  const [hours, minutes] = time.split(":").map(Number);
  return hours * 60 + minutes;
}


// Get segment color classes
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

// Get action icon
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

export function PrecoolingSchedule({
  schedule,
  currentTime,
  readinessChecks,
  onSegmentClick,
  onActionClick
}: PrecoolingScheduleProps) {
  const [hoveredAction, setHoveredAction] = useState<string | null>(null);
  const [selectedSegment, setSelectedSegment] = useState<string | null>(null);

  // Calculate timeline dimensions
  const timelineStart = Math.min(...schedule.map(s => timeToMinutes(s.start)));
  const timelineEnd = Math.max(...schedule.map(s => timeToMinutes(s.end)));
  const timelineDuration = timelineEnd - timelineStart;
  const currentMinutes = timeToMinutes(currentTime);

  // Check if current time is within timeline
  const isCurrentTimeInTimeline = currentMinutes >= timelineStart && currentMinutes <= timelineEnd;

  // Calculate countdown to next action
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

  // Handle segment click
  const handleSegmentClick = (segment: ScheduleSegment) => {
    setSelectedSegment(segment.label);
    onSegmentClick?.(segment);
  };

  // Handle action hover
  const handleActionHover = (actionTime: string) => {
    setHoveredAction(actionTime);
  };

  // Calculate position percentage on timeline
  function getPositionPercent(time: string): number {
    const minutes = timeToMinutes(time);
    return ((minutes - timelineStart) / timelineDuration) * 100;
  }

  // Calculate width percentage for segment
  function getSegmentWidth(start: string, end: string): number {
    const startMinutes = timeToMinutes(start);
    const endMinutes = timeToMinutes(end);
    return ((endMinutes - startMinutes) / timelineDuration) * 100;
  }

  return (
    <Card>
      <div className="flex items-center justify-between mb-6">
        <div>
          <Title>Pre-cooling Schedule Timeline</Title>
          <Text>Visualization of optimization actions before and during load shedding</Text>
        </div>
        {nextAction && (
          <div className="flex items-center gap-2 bg-gray-800 px-3 py-2 rounded">
            <Clock className="h-4 w-4 text-blue-400" />
            <div>
              <Text className="text-sm">Next action in</Text>
              <Text className="font-medium">{countdownMinutes} min</Text>
            </div>
          </div>
        )}
      </div>

      {/* Main Timeline */}
      <div className="relative mb-8">
        {/* Timeline track */}
        <div className="h-2 bg-gray-800 rounded-full relative">
          {/* Current time indicator */}
          {isCurrentTimeInTimeline && (
            <div
              className="absolute top-1/2 transform -translate-y-1/2 w-1 h-6 bg-white z-20"
              style={{ left: `${getPositionPercent(currentTime)}%` }}
            >
              <div className="absolute -top-6 left-1/2 transform -translate-x-1/2 whitespace-nowrap">
                <Badge color="gray" size="xs">NOW</Badge>
              </div>
            </div>
          )}

          {/* Timeline segments */}
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
                {/* Segment label */}
                <div className="absolute -top-8 left-1/2 transform -translate-x-1/2 whitespace-nowrap">
                  <Badge color={segment.type === "precooling" ? "blue" : segment.type === "load_shedding" ? "red" : "green"} size="xs">
                    {segment.label}
                  </Badge>
                </div>

                {/* Action markers within segment */}
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
                        {/* Action time label */}
                        <div className="absolute -bottom-6 left-1/2 transform -translate-x-1/2 whitespace-nowrap">
                          <Text className="text-xs font-medium">{action.time}</Text>
                        </div>
                      </div>
                  );
                })}
              </div>
            );
          })}

          {/* Time markers */}
          <div className="absolute -bottom-8 left-0 right-0 flex justify-between">
            {schedule.map((segment, idx) => (
              <div key={idx} className="flex flex-col items-center">
                <Text className="text-xs text-gray-400">{segment.start}</Text>
                {idx === schedule.length - 1 && (
                  <Text className="text-xs text-gray-400 mt-1">{segment.end}</Text>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Segment details panel */}
        {selectedSegment && (
          <div className="mt-12 p-4 bg-gray-800 rounded">
            <div className="flex items-center justify-between mb-3">
              <Title className="text-lg">Segment Details</Title>
              <Badge
                color={schedule.find(s => s.label === selectedSegment)?.type === "precooling" ? "blue" :
                       schedule.find(s => s.label === selectedSegment)?.type === "load_shedding" ? "red" : "green"}
              >
                {selectedSegment}
              </Badge>
            </div>
            {schedule
              .filter(s => s.label === selectedSegment)
              .map((segment, idx) => (
                <div key={idx} className="space-y-3">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Text className="text-sm text-gray-400">Start Time</Text>
                      <Text className="font-medium">{segment.start}</Text>
                    </div>
                    <div>
                      <Text className="text-sm text-gray-400">End Time</Text>
                      <Text className="font-medium">{segment.end}</Text>
                    </div>
                  </div>
                  <div>
                    <Text className="text-sm text-gray-400 mb-2">Actions</Text>
                    <div className="space-y-2">
                      {segment.actions.map((action, actionIdx) => (
                        <div key={actionIdx} className="flex items-center gap-3 p-2 bg-gray-900 rounded">
                          <div className="flex-shrink-0">
                            {getActionIcon(action.action)}
                          </div>
                          <div className="flex-grow">
                            <Text className="font-medium">{action.action}</Text>
                            <Text className="text-sm text-gray-400">{action.value}</Text>
                          </div>
                          <Badge color="gray" size="xs">{action.time}</Badge>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
          </div>
        )}
      </div>

      {/* Generator Readiness Checks */}
      <div className="border-t border-gray-700 pt-6">
        <Title className="text-lg">Generator Readiness Checks</Title>
        <Text className="mb-4">System verification before load shedding begins</Text>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {readinessChecks.map((check, idx) => (
            <div
              key={idx}
              className={`p-4 rounded ${check.passed ? 'bg-green-900/20 border border-green-500/30' : 'bg-red-900/20 border border-red-500/30'}`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  {check.passed ? (
                    <CheckCircle className="h-5 w-5 text-green-400" />
                  ) : (
                    <AlertTriangle className="h-5 w-5 text-red-400" />
                  )}
                  <Text className="font-medium">{check.check}</Text>
                </div>
                <Badge color={check.passed ? "emerald" : "red"} size="xs">
                  {check.passed ? "PASSED" : "FAILED"}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <Text className="text-sm text-gray-400">Status</Text>
                <Text className={`font-medium ${check.passed ? 'text-green-400' : 'text-red-400'}`}>
                  {check.status}
                </Text>
              </div>
              <div className="flex items-center justify-between mt-2">
                <Text className="text-sm text-gray-400">Time</Text>
                <Text className="text-sm text-gray-400">{check.time}</Text>
              </div>
            </div>
          ))}
        </div>

        {/* Overall status */}
        <div className="mt-6 p-4 bg-gray-800 rounded">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {readinessChecks.every(c => c.passed) ? (
                <>
                  <CheckCircle className="h-6 w-6 text-green-400" />
                  <div>
                    <Text className="font-medium">All checks passed</Text>
                    <Text className="text-sm text-gray-400">Generator ready for load shedding</Text>
                  </div>
                </>
              ) : (
                <>
                  <AlertTriangle className="h-6 w-6 text-red-400" />
                  <div>
                    <Text className="font-medium">Checks require attention</Text>
                    <Text className="text-sm text-gray-400">
                      {readinessChecks.filter(c => !c.passed).length} of {readinessChecks.length} checks failed
                    </Text>
                  </div>
                </>
              )}
            </div>
            <Badge color={readinessChecks.every(c => c.passed) ? "emerald" : "red"} size="lg">
              {readinessChecks.every(c => c.passed) ? "READY" : "NOT READY"}
            </Badge>
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="mt-6 pt-6 border-t border-gray-700">
        <span className="text-sm font-medium mb-3" style={{ color: 'var(--color-sentinel-text-primary)' }}>Timeline Legend</span>
        <div className="flex flex-wrap gap-4">
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded bg-blue-900/20 border border-blue-500/50"></div>
            <Text className="text-sm">Pre-cooling phase</Text>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded bg-red-900/20 border border-red-500/50"></div>
            <Text className="text-sm">Load shedding phase</Text>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded bg-green-900/20 border border-green-500/50"></div>
            <Text className="text-sm">Recovery phase</Text>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-full border-2 border-blue-400"></div>
            <Text className="text-sm">Action marker (click for details)</Text>
          </div>
        </div>
      </div>
    </Card>
  );
}

// Default props for local fallback mode
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
