/**
 * OptimizationPanel Component - Load Shedding Optimization Interface
 *
 * Three-column layout showing:
 * 1. Eskom status and schedule
 * 2. Thermal runway visualization
 * 3. Pre-cooling schedule and actions
 *
 * Follows SENTINEL dark theme design.
 */

import { useState, useEffect } from "react";
import { Card, Title, Text, Badge, Button } from "@tremor/react";
import { Zap, Clock, Thermometer, CheckCircle, Play, Eye } from "lucide-react";
import { ThermalRunwayChart } from "./ThermalRunwayChart";
import type {
  EskomStatusResponse,
  SiteScheduleResponse,
  ThermalRunwayResponse
} from "../lib/api";

interface OptimizationPanelProps {
  siteId?: string;
  scenarioId?: string;
  compact?: boolean;
}

// Mock data for development
const mockEskomStatus: EskomStatusResponse = {
  current_stage: 4,
  updated_at: new Date().toISOString(),
  next_stages: [
    { stage: 4, start_time: "16:00", end_time: "18:30" },
    { stage: 3, start_time: "18:30", end_time: "20:30" },
    { stage: 2, start_time: "20:30", end_time: "22:30" }
  ],
  area_schedules: {}
};

const mockSiteSchedule: SiteScheduleResponse = {
  site_id: "site-001",
  site_name: "Gateway Theatre",
  current_stage: 4,
  schedules: [
    { stage: 4, start_time: "16:00", end_time: "18:30" },
    { stage: 3, start_time: "20:00", end_time: "22:00" }
  ],
  next_outage: { stage: 4, start_time: "16:00", end_time: "18:30" }
};

const mockThermalRunway: ThermalRunwayResponse = {
  site_id: "site-001",
  site_name: "Gateway Theatre",
  current_temperature: 22.4,
  comfort_limit: 26.0,
  thermal_runway_minutes: 52,
  comfort_breach_time: "16:52",
  calculation_method: "thermal_model",
  building_params: {
    thermal_mass: 0.8,
    insulation_factor: 0.6,
    internal_heat_gain: 0.5
  },
  weather_forecast: {
    outside_temp: 32.0,
    solar_load: 0.7,
    humidity: 65
  }
};

const mockPrecoolingSchedule = {
  start: "14:45",
  duration_minutes: 45,
  target_temp: 20.0,
  actions: [
    { time: "14:45", action: "CHW setpoint", value: "6°C → 5°C", description: "Reduce chilled water setpoint" },
    { time: "14:50", action: "AHU fan speed", value: "70% → 85%", description: "Increase air circulation" },
    { time: "15:00", action: "Night purge", value: "Enabled", description: "Use outside air cooling" },
    { time: "15:15", action: "VAV optimization", value: "Balanced", description: "Uniform cooling distribution" },
    { time: "15:30", action: "Temperature check", value: "20.5°C", description: "Target achieved" }
  ],
  energy_impact_kwh: 85,
  peak_demand_increase_percent: 12
};

const mockGeneratorReadiness = [
  { check: "Generator test", status: "PASSED", time: "13:45" },
  { check: "UPS status", status: "96% capacity", time: "Current" },
  { check: "Fuel level", status: "85%", time: "Current" }
];

// Get stage badge color
function getStageColor(stage: number): string {
  if (stage === 0) return "emerald";
  if (stage <= 2) return "yellow";
  if (stage <= 4) return "orange";
  return "red";
}


export function OptimizationPanel({ siteId = "site-001", scenarioId, compact = false }: OptimizationPanelProps) {
  const [eskomStatus, setEskomStatus] = useState<EskomStatusResponse | null>(mockEskomStatus);
  const [siteSchedule, setSiteSchedule] = useState<SiteScheduleResponse | null>(mockSiteSchedule);
  const [thermalRunway, setThermalRunway] = useState<ThermalRunwayResponse | null>(mockThermalRunway);
  const [loading, setLoading] = useState(false);
  // Load data on mount
  useEffect(() => {
    // TODO: Replace with actual API calls
    setLoading(true);
    setTimeout(() => {
      setEskomStatus(mockEskomStatus);
      setSiteSchedule(mockSiteSchedule);
      setThermalRunway(mockThermalRunway);
      setLoading(false);
    }, 500);
  }, [siteId, scenarioId]);

  if (loading) {
    return (
      <Card className="mt-6">
        <div className="animate-pulse space-y-4">
          <div className="h-4 bg-gray-700 rounded w-1/4"></div>
          <div className="h-32 bg-gray-800 rounded"></div>
        </div>
      </Card>
    );
  }

  if (compact) {
    return (
      <Card className="mt-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-blue-400" />
            <Title>Load Shedding Optimization</Title>
          </div>
          <Badge color="emerald">Active</Badge>
        </div>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <Text>Current Stage</Text>
            <Badge color={getStageColor(eskomStatus?.current_stage || 0)} size="lg">
              Stage {eskomStatus?.current_stage || 0}
            </Badge>
          </div>

          <div className="flex items-center justify-between">
            <Text>Next Outage</Text>
            <Text className="font-medium">
              {siteSchedule?.next_outage ?
                `${siteSchedule.next_outage.start_time} - ${siteSchedule.next_outage.end_time}` :
                "None scheduled"}
            </Text>
          </div>

          <div className="flex items-center justify-between">
            <Text>Thermal Runway</Text>
            <Text className="font-medium">
              {thermalRunway?.thermal_runway_minutes || 0} min
            </Text>
          </div>

          <Button size="xs" variant="secondary" icon={Eye}>
            View Details
          </Button>
        </div>
      </Card>
    );
  }

  return (
    <div className="mt-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Title>Load Shedding Optimization</Title>
          <Text>Optimize building comfort and energy use during load shedding</Text>
        </div>
        <div className="flex items-center gap-2">
          <Badge color="emerald" size="lg">
            Active Monitoring
          </Badge>
          <Button size="xs" variant="secondary" icon={Play}>
            Start Pre-cool
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Left Column: Eskom Status */}
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Zap className="h-5 w-5 text-blue-400" />
              <Title className="text-lg">Eskom Status</Title>
            </div>
            <Badge color={getStageColor(eskomStatus?.current_stage || 0)} size="lg">
              Stage {eskomStatus?.current_stage || 0}
            </Badge>
          </div>

          <div className="space-y-4">
            <div>
              <Text className="font-medium mb-2">Next Outages</Text>
              <div className="space-y-2">
                {siteSchedule?.schedules?.map((schedule, idx) => (
                  <div key={idx} className="flex items-center justify-between p-2 bg-gray-800 rounded">
                    <div className="flex items-center gap-2">
                      <Clock className="h-4 w-4 text-gray-400" />
                      <Text>{schedule.start_time} - {schedule.end_time}</Text>
                    </div>
                    <Badge color={getStageColor(schedule.stage)} size="sm">
                      Stage {schedule.stage}
                    </Badge>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <Text className="font-medium mb-2">Area Status</Text>
              <div className="p-3 bg-gray-800 rounded">
                <Text className="font-medium">{siteSchedule?.site_name}</Text>
                <Text className="text-sm text-gray-400">
                  {siteSchedule?.next_outage ?
                    `Next outage: ${siteSchedule.next_outage.start_time}-${siteSchedule.next_outage.end_time}` :
                    "No outages scheduled"}
                </Text>
              </div>
            </div>

            <div className="pt-2 border-t border-gray-700">
              <Text className="text-sm text-gray-400">
                Updated: {new Date(eskomStatus?.updated_at || "").toLocaleTimeString()}
              </Text>
            </div>
          </div>
        </Card>

        {/* Middle Column: Thermal Runway */}
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Thermometer className="h-5 w-5 text-orange-400" />
              <Title className="text-lg">Thermal Runway</Title>
            </div>
            <Badge color={thermalRunway?.thermal_runway_minutes && thermalRunway.thermal_runway_minutes > 60 ? "emerald" : "orange"}>
              {thermalRunway?.thermal_runway_minutes || 0} min
            </Badge>
          </div>

          {thermalRunway && (
            <div className="space-y-4">
              <ThermalRunwayChart
                data={{
                  timePoints: ["14:30", "15:00", "15:30", "16:00", "16:30", "17:00", "17:30", "18:00", "18:30"],
                  withoutPrecooling: [22.4, 23.1, 24.0, 24.9, 25.7, 26.5, 27.3, 28.1, 28.9],
                  withPrecooling: [22.4, 21.8, 21.2, 21.5, 22.1, 22.9, 23.8, 24.7, 25.5],
                  comfortLimit: 26.0
                }}
                outagePeriod={{ start: "16:00", end: "18:30" }}
                metrics={{
                  runwayWithout: 52,
                  runwayWith: 108,
                  comfortBreachTime: "16:52",
                  recoveryTime: "19:00"
                }}
              />

              <div className="grid grid-cols-2 gap-4">
                <div className="p-3 bg-gray-800 rounded">
                  <Text className="text-sm text-gray-400">Without Pre-cooling</Text>
                  <Text className="text-xl font-bold">52 min</Text>
                  <Text className="text-sm text-gray-400">Breach at 16:52</Text>
                </div>
                <div className="p-3 bg-blue-900/30 rounded border border-blue-700/50">
                  <Text className="text-sm text-blue-300">With SENTINEL</Text>
                  <Text className="text-xl font-bold text-blue-300">1h 48min</Text>
                  <Text className="text-sm text-blue-300/80">Comfort maintained</Text>
                </div>
              </div>
            </div>
          )}
        </Card>

        {/* Right Column: Pre-cooling Schedule */}
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Clock className="h-5 w-5 text-green-400" />
              <Title className="text-lg">Pre-cooling Schedule</Title>
            </div>
            <Button size="xs" variant="primary" icon={Play}>
              Start Now
            </Button>
          </div>

          <div className="space-y-4">
            <div>
              <Text className="font-medium mb-2">Timeline</Text>
              <div className="space-y-2">
                {mockPrecoolingSchedule.actions.map((action, idx) => (
                  <div key={idx} className="flex items-start gap-3 p-2 bg-gray-800 rounded">
                    <div className="flex-shrink-0 w-12">
                      <Badge color="blue" size="sm">
                        {action.time}
                      </Badge>
                    </div>
                    <div className="flex-grow">
                      <Text className="font-medium">{action.action}</Text>
                      <Text className="text-sm text-gray-400">{action.value} • {action.description}</Text>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <Text className="font-medium mb-2">Generator Readiness</Text>
              <div className="space-y-2">
                {mockGeneratorReadiness.map((check, idx) => (
                  <div key={idx} className="flex items-center justify-between p-2 bg-gray-800 rounded">
                    <div className="flex items-center gap-2">
                      <CheckCircle className="h-4 w-4 text-emerald-400" />
                      <Text>{check.check}</Text>
                    </div>
                    <div className="text-right">
                      <Text className="font-medium">{check.status}</Text>
                      <Text className="text-xs text-gray-400">{check.time}</Text>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="pt-2 border-t border-gray-700">
              <div className="flex items-center justify-between">
                <Text className="text-sm">Energy Impact</Text>
                <Text className="font-medium">+85 kWh (+12%)</Text>
              </div>
              <Text className="text-sm text-gray-400">
                Pre-cooling uses extra energy now to save generator fuel later
              </Text>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}