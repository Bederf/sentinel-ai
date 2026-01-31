/**
 * EquipmentStatusPanel - HVAC equipment grid with health scores
 *
 * Features:
 * - Equipment cards by type (AHU, FCU, Chiller)
 * - Health score with breakdown
 * - Status indicators
 * - Service/maintenance info
 */

import { useState, useEffect, useRef } from "react";
import { Card, Title, Text, Badge, Flex, Grid, Tab, TabGroup, TabList, TabPanel, TabPanels } from "@tremor/react";
import { Fan, Thermometer, Activity, AlertTriangle, CheckCircle, Clock, Wrench } from "lucide-react";
import { hvacApi, type HVACEquipment } from "../../lib/hvacApi";

interface EquipmentStatusPanelProps {
  siteId?: string;
  compact?: boolean;
  onEquipmentSelect?: (equipment: HVACEquipment) => void;
}

export function EquipmentStatusPanel({ siteId, compact = false, onEquipmentSelect }: EquipmentStatusPanelProps) {
  const [equipment, setEquipment] = useState<HVACEquipment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    async function loadEquipment() {
      try {
        const response = await hvacApi.getEquipment(siteId);
        if (!mountedRef.current) return;
        setEquipment(response.equipment);
        setLoading(false);
      } catch (err) {
        if (!mountedRef.current) return;
        setError(err instanceof Error ? err.message : "Failed to load equipment");
        setLoading(false);
      }
    }

    loadEquipment();
    const interval = setInterval(loadEquipment, 30000);

    return () => {
      mountedRef.current = false;
      clearInterval(interval);
    };
  }, [siteId]);

  function getHealthColor(score: number): "green" | "amber" | "red" {
    if (score >= 80) return "green";
    if (score >= 60) return "amber";
    return "red";
  }

  function getStatusIcon(status: string) {
    switch (status) {
      case "normal":
        return <CheckCircle className="w-4 h-4 text-green-500" />;
      case "warning":
        return <AlertTriangle className="w-4 h-4 text-amber-500" />;
      case "fault":
      case "off":
        return <AlertTriangle className="w-4 h-4 text-red-500" />;
      default:
        return <Activity className="w-4 h-4 text-gray-400" />;
    }
  }

  function getEquipmentIcon(type: string) {
    switch (type) {
      case "ahu":
        return <Fan className="w-5 h-5" style={{ color: "var(--color-sentinel-blue)" }} />;
      case "fcu":
        return <Fan className="w-5 h-5" style={{ color: "var(--color-sentinel-green)" }} />;
      case "chiller":
        return <Thermometer className="w-5 h-5" style={{ color: "var(--color-sentinel-cyan)" }} />;
      case "cooling_tower":
        return <Activity className="w-5 h-5" style={{ color: "var(--color-sentinel-purple)" }} />;
      default:
        return <Activity className="w-5 h-5" style={{ color: "var(--color-sentinel-text-secondary)" }} />;
    }
  }

  if (loading) {
    return (
      <Card>
        <Title>Equipment Status</Title>
        <div className="animate-pulse space-y-4 mt-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-32 bg-gray-200 rounded" />
          ))}
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <Title>Equipment Status</Title>
        <Text className="text-red-500 mt-4">{error}</Text>
      </Card>
    );
  }

  // Group equipment by type
  const equipmentByType = equipment.reduce((acc, eq) => {
    const type = eq.type;
    if (!acc[type]) acc[type] = [];
    acc[type].push(eq);
    return acc;
  }, {} as Record<string, HVACEquipment[]>);

  const typeLabels: Record<string, string> = {
    ahu: "AHUs",
    fcu: "FCUs",
    chiller: "Chillers",
    cooling_tower: "Cooling Towers",
    vav: "VAV Boxes",
    pump: "Pumps",
    crac: "CRACs",
  };

  const types = Object.keys(equipmentByType);

  const EquipmentCard = ({ eq }: { eq: HVACEquipment }) => (
    <Card
      className="cursor-pointer hover:ring-2 hover:ring-blue-500/30 transition-all"
      decoration="top"
      decorationColor={getHealthColor(eq.calculated_health || eq.health_score)}
      onClick={() => onEquipmentSelect?.(eq)}
    >
      {/* Header */}
      <Flex justifyContent="between" alignItems="start" className="mb-3">
        <Flex alignItems="center" className="gap-2">
          {getEquipmentIcon(eq.type)}
          <div>
            <Text className="font-medium">{eq.name}</Text>
            <Text className="text-xs text-gray-400">{eq.location}</Text>
          </div>
        </Flex>
        <div className="flex items-center gap-2">
          {getStatusIcon(eq.status)}
          <Badge color={eq.status === "normal" ? "green" : "red"} size="xs">
            {eq.status}
          </Badge>
        </div>
      </Flex>

      {/* Health Score */}
      <div
        className="p-3 rounded-lg mb-3"
        style={{ background: "var(--color-sentinel-bg-secondary)" }}
      >
        <Flex justifyContent="between" alignItems="center" className="mb-2">
          <Text className="text-sm">Health Score</Text>
          <Badge
            color={getHealthColor(eq.calculated_health || eq.health_score)}
            size="lg"
          >
            {(eq.calculated_health || eq.health_score).toFixed(0)}%
          </Badge>
        </Flex>

        {/* Health Factors Breakdown */}
        {!compact && eq.health_factors && (
          <div className="space-y-1">
            {Object.entries(eq.health_factors).map(([key, factor]) => (
              <Flex
                key={key}
                justifyContent="between"
                alignItems="center"
                className="text-xs"
              >
                <span className="text-gray-400 capitalize">
                  {key.replace("_", " ")}
                </span>
                <Flex alignItems="center" className="gap-2">
                  <div
                    className="w-16 h-1.5 rounded-full overflow-hidden"
                    style={{ background: "var(--color-sentinel-border)" }}
                  >
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${factor.score}%`,
                        background:
                          factor.score >= 80
                            ? "var(--color-sentinel-green)"
                            : factor.score >= 60
                            ? "var(--color-sentinel-amber)"
                            : "var(--color-sentinel-red)",
                      }}
                    />
                  </div>
                  <span className="text-gray-500 w-12">{factor.value}</span>
                </Flex>
              </Flex>
            ))}
          </div>
        )}
      </div>

      {/* Equipment Info */}
      {!compact && (
        <div className="space-y-2 text-xs text-gray-400">
          <Flex justifyContent="between">
            <span>Manufacturer</span>
            <span className="text-gray-300">{eq.manufacturer}</span>
          </Flex>
          <Flex justifyContent="between">
            <span>Model</span>
            <span className="text-gray-300">{eq.model}</span>
          </Flex>
          <Flex justifyContent="between">
            <span>Capacity</span>
            <span className="text-gray-300">{eq.capacity}</span>
          </Flex>
          <Flex justifyContent="between" alignItems="center">
            <Flex alignItems="center" className="gap-1">
              <Wrench className="w-3 h-3" />
              <span>Last Service</span>
            </Flex>
            <span className="text-gray-300">
              {eq.last_service
                ? new Date(eq.last_service).toLocaleDateString()
                : "N/A"}
            </span>
          </Flex>
          <Flex justifyContent="between" alignItems="center">
            <Flex alignItems="center" className="gap-1">
              <Clock className="w-3 h-3" />
              <span>Installed</span>
            </Flex>
            <span className="text-gray-300">
              {eq.install_date
                ? new Date(eq.install_date).toLocaleDateString()
                : "N/A"}
            </span>
          </Flex>
        </div>
      )}
    </Card>
  );

  if (compact) {
    return (
      <div className="space-y-3">
        <Flex justifyContent="between" alignItems="center">
          <Text className="font-medium">Equipment</Text>
          <Badge color="gray">{equipment.length} total</Badge>
        </Flex>
        <Grid numItems={2} className="gap-2">
          {equipment.slice(0, 4).map((eq) => (
            <EquipmentCard key={eq.id} eq={eq} />
          ))}
        </Grid>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Flex justifyContent="between" alignItems="center">
        <div>
          <Title>Equipment Status</Title>
          <Text>{equipment.length} HVAC equipment items</Text>
        </div>
        <div className="flex gap-2">
          <Badge color="green">
            {equipment.filter((e) => e.health_status === "healthy").length} Healthy
          </Badge>
          <Badge color="amber">
            {equipment.filter((e) => e.health_status === "attention").length} Attention
          </Badge>
          <Badge color="red">
            {equipment.filter((e) => e.health_status === "critical").length} Critical
          </Badge>
        </div>
      </Flex>

      <TabGroup index={activeTab} onIndexChange={setActiveTab}>
        <TabList className="mb-4">
          <Tab>All</Tab>
          {types.map((type) => (
            <Tab key={type}>
              {typeLabels[type] || type.toUpperCase()} ({equipmentByType[type].length})
            </Tab>
          ))}
        </TabList>

        <TabPanels>
          <TabPanel>
            <Grid numItems={3} className="gap-4">
              {equipment.map((eq) => (
                <EquipmentCard key={eq.id} eq={eq} />
              ))}
            </Grid>
          </TabPanel>

          {types.map((type) => (
            <TabPanel key={type}>
              <Grid numItems={3} className="gap-4">
                {equipmentByType[type].map((eq) => (
                  <EquipmentCard key={eq.id} eq={eq} />
                ))}
              </Grid>
            </TabPanel>
          ))}
        </TabPanels>
      </TabGroup>
    </div>
  );
}

export default EquipmentStatusPanel;
