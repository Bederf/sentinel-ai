/**
 * ZoneOverviewPanel - Grid view of HVAC zones with status and setpoint control
 *
 * Features:
 * - Zone status cards with temperature display
 * - Inline setpoint adjustment
 * - Temperature deviation indicators
 * - FCU/AHU association display
 */

import { useState, useEffect, useRef } from "react";
import { Card, Title, Text, Badge, Flex, Grid, Button } from "@tremor/react";
import { Thermometer, AlertTriangle, Fan, Settings } from "lucide-react";
import { hvacApi, type HVACZone } from "../../lib/hvacApi";
import TemperatureControl from "../TemperatureControl";

interface ZoneOverviewPanelProps {
  siteId?: string;
  compact?: boolean;
  onZoneSelect?: (zone: HVACZone) => void;
}

export function ZoneOverviewPanel({ siteId, compact = false, onZoneSelect }: ZoneOverviewPanelProps) {
  const [zones, setZones] = useState<HVACZone[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingZone, setEditingZone] = useState<string | null>(null);
  const mountedRef = useRef(true);
  const loadZonesRef = useRef<() => Promise<void>>();

  useEffect(() => {
    mountedRef.current = true;

    async function loadZones() {
      try {
        const response = await hvacApi.getZones(siteId);
        if (!mountedRef.current) return;
        setZones(response.zones);
        setLoading(false);
      } catch (err) {
        if (!mountedRef.current) return;
        setError(err instanceof Error ? err.message : "Failed to load zones");
        setLoading(false);
      }
    }

    loadZonesRef.current = loadZones;
    loadZones();
    const interval = setInterval(loadZones, 30000);

    return () => {
      mountedRef.current = false;
      clearInterval(interval);
    };
  }, [siteId]);

  async function handleSetpointChange(zoneId: string, newSetpoint: number) {
    try {
      await hvacApi.setZoneSetpoint(zoneId, newSetpoint);
      setEditingZone(null);
      loadZonesRef.current?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update setpoint");
    }
  }

  function getStatusColor(status: string): "green" | "amber" | "red" | "gray" {
    switch (status) {
      case "running":
        return "green";
      case "fault":
        return "red";
      case "offline":
        return "gray";
      default:
        return "amber";
    }
  }

  function getDeviationColor(deviation: number): string {
    const abs = Math.abs(deviation);
    if (abs <= 1) return "var(--color-sentinel-green)";
    if (abs <= 2) return "var(--color-sentinel-amber)";
    return "var(--color-sentinel-red)";
  }

  if (loading) {
    return (
      <Card>
        <Title>Zone Overview</Title>
        <div className="animate-pulse space-y-4 mt-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 bg-gray-200 rounded" />
          ))}
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <Title>Zone Overview</Title>
        <Text className="text-red-500 mt-4">{error}</Text>
        <Button size="xs" className="mt-2" onClick={() => { setError(null); loadZones(); }}>
          Retry
        </Button>
      </Card>
    );
  }

  // Group zones by floor
  const zonesByFloor = zones.reduce((acc, zone) => {
    const floor = zone.floor || "Unknown";
    if (!acc[floor]) acc[floor] = [];
    acc[floor].push(zone);
    return acc;
  }, {} as Record<string, HVACZone[]>);

  return (
    <div className="space-y-4">
      {!compact && (
        <Flex justifyContent="between" alignItems="center" className="mb-4">
          <div>
            <Title>Zone Overview</Title>
            <Text>{zones.length} zones configured</Text>
          </div>
          <div className="flex gap-2">
            <Badge color="green">{zones.filter(z => z.status === "running").length} Running</Badge>
            <Badge color="red">{zones.filter(z => z.status === "fault").length} Fault</Badge>
          </div>
        </Flex>
      )}

      {Object.entries(zonesByFloor).map(([floor, floorZones]) => (
        <div key={floor}>
          {!compact && (
            <Text className="font-medium text-sm mb-2 text-gray-400">Floor {floor}</Text>
          )}
          <Grid numItems={compact ? 2 : 3} className="gap-3">
            {floorZones.map((zone) => (
              <Card
                key={zone.zone_id}
                className="cursor-pointer hover:ring-2 hover:ring-blue-500/30 transition-all"
                decoration="left"
                decorationColor={getStatusColor(zone.status)}
                onClick={() => !editingZone && onZoneSelect?.(zone)}
              >
                {/* Zone Header */}
                <Flex justifyContent="between" alignItems="start" className="mb-3">
                  <div>
                    <Text className="font-medium">{zone.zone_name}</Text>
                    <Text className="text-xs text-gray-400">
                      {zone.fcu_id || zone.ahu_id || "No FCU"}
                    </Text>
                  </div>
                  <Badge color={getStatusColor(zone.status)} size="xs">
                    {zone.status}
                  </Badge>
                </Flex>

                {/* Temperature Display */}
                <div className="mb-3">
                  <Flex alignItems="baseline" className="gap-1">
                    <span
                      className="text-3xl font-bold"
                      style={{ color: getDeviationColor(zone.temp_deviation) }}
                    >
                      {zone.current_temp.toFixed(1)}
                    </span>
                    <span className="text-gray-400">°C</span>
                  </Flex>

                  {/* Deviation indicator */}
                  {Math.abs(zone.temp_deviation) > 0.5 && (
                    <Flex alignItems="center" className="gap-1 mt-1">
                      <AlertTriangle
                        className="w-3 h-3"
                        style={{ color: getDeviationColor(zone.temp_deviation) }}
                      />
                      <Text
                        className="text-xs"
                        style={{ color: getDeviationColor(zone.temp_deviation) }}
                      >
                        {zone.temp_deviation > 0 ? "+" : ""}
                        {zone.temp_deviation.toFixed(1)}°C from setpoint
                      </Text>
                    </Flex>
                  )}
                </div>

                {/* Setpoint Control */}
                {editingZone === zone.zone_id ? (
                  <div onClick={(e) => e.stopPropagation()}>
                    <TemperatureControl
                      label="Setpoint"
                      unit="°C"
                      value={zone.setpoint}
                      min={zone.temp_min}
                      max={zone.temp_max}
                      step={0.5}
                      onChange={(value) => handleSetpointChange(zone.zone_id, value)}
                      disabled={zone.status === "offline"}
                    />
                    <Button
                      size="xs"
                      variant="secondary"
                      className="mt-2"
                      onClick={() => setEditingZone(null)}
                    >
                      Cancel
                    </Button>
                  </div>
                ) : (
                  <Flex
                    justifyContent="between"
                    alignItems="center"
                    className="p-2 rounded"
                    style={{ background: "var(--color-sentinel-bg-secondary)" }}
                  >
                    <Flex alignItems="center" className="gap-2">
                      <Thermometer
                        className="w-4 h-4"
                        style={{ color: "var(--color-sentinel-blue)" }}
                      />
                      <Text className="text-sm">
                        Setpoint: <span className="font-medium">{zone.setpoint}°C</span>
                      </Text>
                    </Flex>
                    <Button
                      size="xs"
                      variant="secondary"
                      icon={Settings}
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingZone(zone.zone_id);
                      }}
                      disabled={zone.status === "offline"}
                    >
                      Adjust
                    </Button>
                  </Flex>
                )}

                {/* Equipment Info */}
                {!compact && (
                  <Flex className="mt-3 gap-4 text-xs text-gray-400">
                    {zone.fcu_id && (
                      <Flex alignItems="center" className="gap-1">
                        <Fan className="w-3 h-3" />
                        <span>{zone.fcu_id}</span>
                        {zone.fcu_health !== undefined && zone.fcu_health !== null && (
                          <Badge
                            color={zone.fcu_health >= 80 ? "green" : zone.fcu_health >= 60 ? "amber" : "red"}
                            size="xs"
                          >
                            {zone.fcu_health}%
                          </Badge>
                        )}
                      </Flex>
                    )}
                    <span>Area: {zone.area_sqm}m²</span>
                    <span>Occ: {zone.typical_occupancy}</span>
                  </Flex>
                )}
              </Card>
            ))}
          </Grid>
        </div>
      ))}
    </div>
  );
}

export default ZoneOverviewPanel;
