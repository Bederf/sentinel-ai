/**
 * ThermalOptimizationPanel - Pre-cooling and thermal runway visualization
 *
 * Features:
 * - Wraps ThermalRunwayChart and PrecoolingSchedule
 * - Fetches thermal data from HVAC API
 * - Shows load shedding preparedness
 */

import { useState, useEffect, useRef } from "react";
import { Card, Title, Text, Badge, Flex, Grid, Tab, TabGroup, TabList, TabPanel, TabPanels } from "@tremor/react";
import { Thermometer, Clock, Zap, AlertTriangle } from "lucide-react";
import { hvacApi, type ThermalRunway } from "../../lib/hvacApi";
import { ThermalRunwayChart } from "../ThermalRunwayChart";
import { PrecoolingSchedule } from "../PrecoolingSchedule";

interface ThermalOptimizationPanelProps {
  siteId: string;
  compact?: boolean;
}

export function ThermalOptimizationPanel({ siteId, compact = false }: ThermalOptimizationPanelProps) {
  const [thermalData, setThermalData] = useState<ThermalRunway | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    async function loadThermalData() {
      try {
        const data = await hvacApi.getThermalRunway(siteId);
        if (!mountedRef.current) return;
        setThermalData(data);
        setLoading(false);
      } catch (err) {
        if (!mountedRef.current) return;
        setError(err instanceof Error ? err.message : "Failed to load thermal data");
        setLoading(false);
      }
    }

    loadThermalData();
    const interval = setInterval(loadThermalData, 60000);

    return () => {
      mountedRef.current = false;
      clearInterval(interval);
    };
  }, [siteId]);

  if (loading) {
    return (
      <Card>
        <Title>Thermal Optimization</Title>
        <div className="animate-pulse h-64 bg-gray-200 rounded mt-4" />
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <Title>Thermal Optimization</Title>
        <Text className="text-red-500 mt-4">{error}</Text>
      </Card>
    );
  }

  if (!thermalData) {
    return (
      <Card>
        <Title>Thermal Optimization</Title>
        <Text className="text-gray-500 mt-4">No thermal data available</Text>
      </Card>
    );
  }

  const { data, metrics, outage_period, current_conditions } = thermalData;

  // Compact view
  if (compact) {
    return (
      <Card>
        <Flex justifyContent="between" alignItems="center" className="mb-4">
          <Flex alignItems="center" className="gap-2">
            <Thermometer className="w-5 h-5" style={{ color: "var(--color-sentinel-blue)" }} />
            <Text className="font-medium">Thermal Runway</Text>
          </Flex>
          <Badge color="blue" size="lg">
            +{metrics.improvement_percent}% with pre-cooling
          </Badge>
        </Flex>

        <Grid className="grid grid-cols-2 gap-4">
          <div
            className="p-3 rounded-lg"
            style={{ background: "var(--color-sentinel-bg-secondary)" }}
          >
            <Text className="text-xs text-gray-400">Without Pre-cooling</Text>
            <Text className="text-2xl font-bold text-gray-400">
              {metrics.runway_without} min
            </Text>
            <Text className="text-xs text-red-400">
              Breach at {metrics.comfort_breach_time}
            </Text>
          </div>
          <div
            className="p-3 rounded-lg border border-blue-500/30"
            style={{ background: "rgba(59, 130, 246, 0.1)" }}
          >
            <Text className="text-xs text-blue-300">With Pre-cooling</Text>
            <Text className="text-2xl font-bold text-blue-300">
              {metrics.runway_with} min
            </Text>
            <Text className="text-xs text-green-400">Comfort maintained</Text>
          </div>
        </Grid>
      </Card>
    );
  }

  // Full view with tabs
  return (
    <div className="space-y-4">
      <Flex justifyContent="between" alignItems="center">
        <div>
          <Title>Thermal Optimization</Title>
          <Text>Load shedding preparation and thermal modeling</Text>
        </div>
        <div className="flex gap-2">
          <Badge color="gray">
            Current: {current_conditions.avg_temperature}°C
          </Badge>
          <Badge color="red">
            Comfort Limit: {current_conditions.comfort_limit}°C
          </Badge>
        </div>
      </Flex>

      {/* Key Metrics Summary */}
      <Card>
        <Grid className="grid grid-cols-4 gap-4">
          <div
            className="p-4 rounded-lg text-center"
            style={{ background: "var(--color-sentinel-bg-secondary)" }}
          >
            <Thermometer className="w-6 h-6 mx-auto mb-2" style={{ color: "var(--color-sentinel-blue)" }} />
            <Text className="text-xs text-gray-400">Current Temp</Text>
            <Text className="text-2xl font-bold">{current_conditions.avg_temperature}°C</Text>
          </div>
          <div
            className="p-4 rounded-lg text-center"
            style={{ background: "var(--color-sentinel-bg-secondary)" }}
          >
            <Clock className="w-6 h-6 mx-auto mb-2" style={{ color: "var(--color-sentinel-amber)" }} />
            <Text className="text-xs text-gray-400">Runway (No Pre-cool)</Text>
            <Text className="text-2xl font-bold text-gray-400">{metrics.runway_without} min</Text>
          </div>
          <div
            className="p-4 rounded-lg text-center border border-blue-500/30"
            style={{ background: "rgba(59, 130, 246, 0.1)" }}
          >
            <Zap className="w-6 h-6 mx-auto mb-2 text-blue-400" />
            <Text className="text-xs text-blue-300">Runway (Pre-cooled)</Text>
            <Text className="text-2xl font-bold text-blue-300">{metrics.runway_with} min</Text>
          </div>
          <div
            className="p-4 rounded-lg text-center border border-green-500/30"
            style={{ background: "rgba(16, 185, 129, 0.1)" }}
          >
            <AlertTriangle className="w-6 h-6 mx-auto mb-2 text-green-400" />
            <Text className="text-xs text-green-300">Improvement</Text>
            <Text className="text-2xl font-bold text-green-300">+{metrics.improvement_percent}%</Text>
          </div>
        </Grid>
      </Card>

      {/* Tabs for different views */}
      <TabGroup index={activeTab} onIndexChange={setActiveTab}>
        <TabList className="mb-4">
          <Tab>Temperature Curves</Tab>
          <Tab>Pre-cooling Schedule</Tab>
        </TabList>

        <TabPanels>
          <TabPanel>
            <Card>
              <ThermalRunwayChart
                data={data}
                outagePeriod={outage_period}
                metrics={{
                  runwayWithout: metrics.runway_without,
                  runwayWith: metrics.runway_with,
                  comfortBreachTime: metrics.comfort_breach_time,
                  recoveryTime: metrics.recovery_time,
                }}
              />
            </Card>
          </TabPanel>

          <TabPanel>
            <PrecoolingSchedule
              schedule={[
                {
                  type: "precooling",
                  start: "14:45",
                  end: outage_period.start,
                  label: "PRE-COOLING",
                  color: "blue",
                  actions: [
                    {
                      time: "14:45",
                      action: "CHW setpoint",
                      value: "7°C → 5°C",
                      description: "Lower chilled water setpoint for maximum pre-cooling",
                    },
                    {
                      time: "14:50",
                      action: "AHU fan speed",
                      value: "70% → 90%",
                      description: "Increase air handling for faster cooling",
                    },
                    {
                      time: "15:30",
                      action: "Temperature check",
                      value: `${(current_conditions.avg_temperature - 2).toFixed(1)}°C`,
                      description: "Verify pre-cooling target achieved",
                    },
                  ],
                },
                {
                  type: "load_shedding",
                  start: outage_period.start,
                  end: outage_period.end,
                  label: "LOAD SHEDDING",
                  color: "red",
                  actions: [
                    {
                      time: outage_period.start,
                      action: "Power loss",
                      value: "Grid offline",
                      description: "Load shedding begins",
                    },
                    {
                      time: "17:30",
                      action: "Monitor",
                      value: `${(current_conditions.avg_temperature + 1.5).toFixed(1)}°C`,
                      description: "Temperature drift within limits",
                    },
                  ],
                },
                {
                  type: "recovery",
                  start: outage_period.end,
                  end: "19:30",
                  label: "RECOVERY",
                  color: "green",
                  actions: [
                    {
                      time: outage_period.end,
                      action: "Power restored",
                      value: "Grid online",
                      description: "Begin staged restart",
                    },
                    {
                      time: "19:00",
                      action: "Temperature recovery",
                      value: `${current_conditions.avg_setpoint}°C`,
                      description: "Return to normal setpoint",
                    },
                  ],
                },
              ]}
              currentTime={new Date().toLocaleTimeString("en-GB", {
                hour: "2-digit",
                minute: "2-digit",
              })}
              readinessChecks={[
                {
                  check: "Chiller status",
                  status: "Normal operation",
                  time: "Current",
                  passed: true,
                },
                {
                  check: "Generator test",
                  status: "PASSED",
                  time: "13:45",
                  passed: true,
                },
                {
                  check: "UPS capacity",
                  status: "96%",
                  time: "Current",
                  passed: true,
                },
              ]}
            />
          </TabPanel>
        </TabPanels>
      </TabGroup>
    </div>
  );
}

export default ThermalOptimizationPanel;
