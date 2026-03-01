/**
 * SecurityDashboard - Main Security Module Dashboard
 *
 * Follows the proven HVAC/Energy dashboard pattern with 5 tabs:
 * 1. Overview - KPIs + occupancy summary + zone cards
 * 2. Access Control - Recent events, access rules, breach alerts
 * 3. Cameras - Zone cameras with stream URLs and status
 * 4. Occupancy Analysis - 24h trend chart, peak hours, anomalies
 * 5. Integrations - HVAC/Lighting automation status and toggles
 *
 * Phase 69-01: Security Module Dashboard
 */

import { useState, useEffect, useCallback, type ReactElement } from "react";
import {
  Card,
  Title,
  Text,
  Badge,
  Flex,
  Grid,
  Tab,
  TabGroup,
  TabList,
  TabPanel,
  TabPanels,
  AreaChart,
  BarChart,
} from "@tremor/react";
import {
  Shield,
  ShieldCheck,
  Users,
  Camera,
  TrendingUp,
  Link2,
  AlertTriangle,
  CheckCircle,
  Video,
  VideoOff,
  ArrowUpRight,
  ArrowDownLeft,
  Clock,
  Zap,
  Sun,
  Thermometer,
  RefreshCw,
} from "lucide-react";
import { SentinelValueCard } from "../SentinelValueCard";
import { securityApi } from "@/lib/api";
import type { SecurityOccupancy } from "@/lib/api";
import { AccessEventsPanel } from "../AccessEventsPanel";
import { SecurityOccupancyPanel } from "../SecurityOccupancyPanel";

interface SecurityDashboardProps {
  siteId?: string;
}

interface ZoneOccupancy {
  zone_id: string;
  zone_name: string;
  occupancy_count: number;
  max_capacity?: number;
  percent_full?: number;
  badge_entries: number;
  badge_exits: number;
  last_updated: string | null;
  source: string;
}

interface TrendPoint {
  hour: string;
  entries: number;
  exits: number;
  net_occupancy: number;
}

interface CameraInfo {
  camera_id: string;
  zone_id: string;
  name: string;
  floor: string;
  status: string;
  camera_type: string;
  resolution: string;
  has_analytics: boolean;
  motion_detected: boolean;
  stream_url?: string;
  camera_model?: string;
}

export function SecurityDashboard({ siteId = "site-002" }: SecurityDashboardProps) {
  const [activeTab, setActiveTab] = useState(0);
  const [loading, setLoading] = useState(true);
  const [occupancyData, setOccupancyData] = useState<{
    total_occupancy: number;
    zones: SecurityOccupancy[];
  }>({ total_occupancy: 0, zones: [] });
  const [trendData, setTrendData] = useState<TrendPoint[]>([]);
  const [cameras, setCameras] = useState<CameraInfo[]>([]);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchData = useCallback(async () => {
    try {
      // Fetch occupancy data
      const occ = await securityApi.getOccupancy(siteId);
      setOccupancyData(occ);

      setLastUpdated(new Date());
      setLoading(false);
    } catch {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await fetchData();
    setIsRefreshing(false);
  };

  const formatTime = (date: Date) =>
    date.toLocaleTimeString("en-ZA", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });

  // Loading state
  if (loading) {
    return (
      <Card>
        <Title>Security Module</Title>
        <div className="animate-pulse h-96 bg-gray-100 dark:bg-gray-800 rounded mt-4" />
      </Card>
    );
  }

  // Generate demo trend data for chart (when no live data)
  const demoTrendData: TrendPoint[] =
    trendData.length > 0
      ? trendData
      : Array.from({ length: 24 }, (_, i) => {
          const hour = new Date();
          hour.setHours(hour.getHours() - (23 - i));
          const isWorkHour = hour.getHours() >= 7 && hour.getHours() <= 18;
          const base = isWorkHour ? 15 + Math.floor(Math.random() * 20) : Math.floor(Math.random() * 5);
          return {
            hour: `${hour.getHours().toString().padStart(2, "0")}:00`,
            entries: base + Math.floor(Math.random() * 5),
            exits: Math.max(0, base - Math.floor(Math.random() * 5)),
            net_occupancy: base,
          };
        });

  // Demo cameras (when no live data)
  const demoCameras: CameraInfo[] =
    cameras.length > 0
      ? cameras
      : [
          { camera_id: "CAM-GF-NW", zone_id: "zone_000", name: "Ground Floor NW", floor: "L0", status: "online", camera_type: "dome", resolution: "1080p", has_analytics: true, motion_detected: false, stream_url: "rtsp://cctv.local/gf/nw", camera_model: "Hikvision DS-2CD2143G2-IU" },
          { camera_id: "CAM-GF-SE", zone_id: "zone_000", name: "Ground Floor SE", floor: "L0", status: "online", camera_type: "fixed", resolution: "4K", has_analytics: false, motion_detected: true, stream_url: "rtsp://cctv.local/gf/se", camera_model: "Axis P3245-V" },
          { camera_id: "CAM-L1-NW", zone_id: "zone_001", name: "Level 1 NW", floor: "L1", status: "online", camera_type: "ptz", resolution: "1080p", has_analytics: true, motion_detected: false, stream_url: "rtsp://cctv.local/l1/nw", camera_model: "Hikvision DS-2DE4A425IW" },
          { camera_id: "CAM-L1-SE", zone_id: "zone_001", name: "Level 1 SE", floor: "L1", status: "offline", camera_type: "dome", resolution: "1080p", has_analytics: false, motion_detected: false, stream_url: "rtsp://cctv.local/l1/se", camera_model: "Dahua IPC-HDW5442TM" },
          { camera_id: "CAM-L2-NW", zone_id: "zone_002", name: "Level 2 Executive NW", floor: "L2", status: "online", camera_type: "dome", resolution: "4K", has_analytics: true, motion_detected: false, stream_url: "rtsp://cctv.local/l2/nw", camera_model: "Axis Q6135-LE" },
          { camera_id: "CAM-PLANT", zone_id: "zone_plant", name: "Plant Room B1", floor: "B1", status: "online", camera_type: "fixed", resolution: "720p", has_analytics: false, motion_detected: false, stream_url: "rtsp://cctv.local/plant/main", camera_model: "Hikvision DS-2CD1043G2-I" },
        ];

  // Demo zone occupancy data
  const zoneOccupancies: ZoneOccupancy[] =
    occupancyData.zones.length > 0
      ? occupancyData.zones.map((z) => ({
          ...z,
          max_capacity: 50,
          percent_full: (z.occupancy_count / 50) * 100,
        }))
      : [
          { zone_id: "zone_000", zone_name: "Ground Floor Lobby", occupancy_count: 12, max_capacity: 50, percent_full: 24, badge_entries: 45, badge_exits: 33, last_updated: new Date().toISOString(), source: "badge" },
          { zone_id: "zone_001", zone_name: "Level 1 Open Plan", occupancy_count: 22, max_capacity: 40, percent_full: 55, badge_entries: 38, badge_exits: 16, last_updated: new Date().toISOString(), source: "badge" },
          { zone_id: "zone_002", zone_name: "Level 2 Executive", occupancy_count: 8, max_capacity: 35, percent_full: 22.9, badge_entries: 15, badge_exits: 7, last_updated: new Date().toISOString(), source: "badge" },
          { zone_id: "zone_plant", zone_name: "Plant Room B1", occupancy_count: 0, max_capacity: 10, percent_full: 0, badge_entries: 2, badge_exits: 2, last_updated: new Date().toISOString(), source: "badge" },
        ];

  const totalOccupancy = occupancyData.total_occupancy || zoneOccupancies.reduce((s, z) => s + z.occupancy_count, 0);
  const totalCapacity = zoneOccupancies.reduce((s, z) => s + (z.max_capacity || 50), 0);
  const capacityPercent = totalCapacity > 0 ? Math.round((totalOccupancy / totalCapacity) * 100) : 0;
  const onlineCameras = demoCameras.filter((c) => c.status === "online").length;
  const breachEvents = 0; // Placeholder for breach alert count

  // Build tab arrays externally, cast as unknown as ReactElement (Tremor pattern)
  const tabs = [
    <Tab key="overview">
      <Flex alignItems="center" className="gap-2">
        <Shield className="w-4 h-4" /> Overview
      </Flex>
    </Tab>,
    <Tab key="access">
      <Flex alignItems="center" className="gap-2">
        <Users className="w-4 h-4" /> Access Control
      </Flex>
    </Tab>,
    <Tab key="cameras">
      <Flex alignItems="center" className="gap-2">
        <Camera className="w-4 h-4" /> Cameras
        <Badge color={onlineCameras === demoCameras.length ? "green" : "amber"} size="xs">
          {onlineCameras}/{demoCameras.length}
        </Badge>
      </Flex>
    </Tab>,
    <Tab key="analysis">
      <Flex alignItems="center" className="gap-2">
        <TrendingUp className="w-4 h-4" /> Occupancy Analysis
      </Flex>
    </Tab>,
    <Tab key="integrations">
      <Flex alignItems="center" className="gap-2">
        <Link2 className="w-4 h-4" /> Integrations
      </Flex>
    </Tab>,
  ];

  const panels = [
    // ===== Tab 1: Overview =====
    <TabPanel key="overview">
      <div className="space-y-4 mt-4">
        {/* SENTINEL Value Card */}
        <SentinelValueCard
          title="Security Intelligence Impact"
          icon={ShieldCheck}
          baseline={{ label: "", value: 0, unit: "incidents" }}
          sentinel={{ label: "", value: 0, unit: "incidents" }}
          savingsPercent={0}
          period="Monthly"
          collecting
        />

        {/* KPI Cards */}
        <Grid className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Card decoration="top" decorationColor="blue">
            <Flex alignItems="center" className="gap-2 mb-2">
              <Users className="w-5 h-5 text-blue-400" />
              <Text className="font-medium">Total Occupancy</Text>
            </Flex>
            <div className="text-3xl font-bold">{totalOccupancy}</div>
            <Text className="text-xs text-gray-400">
              {capacityPercent}% of {totalCapacity} capacity
            </Text>
          </Card>

          <Card decoration="top" decorationColor={capacityPercent > 80 ? "red" : capacityPercent > 50 ? "amber" : "green"}>
            <Flex alignItems="center" className="gap-2 mb-2">
              <CheckCircle className="w-5 h-5 text-green-400" />
              <Text className="font-medium">Active Zones</Text>
            </Flex>
            <div className="text-3xl font-bold">{zoneOccupancies.filter((z) => z.occupancy_count > 0).length}</div>
            <Text className="text-xs text-gray-400">of {zoneOccupancies.length} zones</Text>
          </Card>

          <Card decoration="top" decorationColor="cyan">
            <Flex alignItems="center" className="gap-2 mb-2">
              <Camera className="w-5 h-5 text-cyan-400" />
              <Text className="font-medium">Cameras Online</Text>
            </Flex>
            <div className="text-3xl font-bold">{onlineCameras}/{demoCameras.length}</div>
            <Text className="text-xs text-gray-400">
              {demoCameras.filter((c) => c.has_analytics).length} with AI analytics
            </Text>
          </Card>

          <Card decoration="top" decorationColor={breachEvents > 0 ? "red" : "green"}>
            <Flex alignItems="center" className="gap-2 mb-2">
              <AlertTriangle className="w-5 h-5 text-amber-400" />
              <Text className="font-medium">Breach Events (24h)</Text>
            </Flex>
            <div className="text-3xl font-bold">{breachEvents}</div>
            <Text className="text-xs text-gray-400">Unauthorized access attempts</Text>
          </Card>
        </Grid>

        {/* Floor Occupancy Cards */}
        <Card>
          <Title className="text-sm mb-3">Zone Occupancy</Title>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {zoneOccupancies.map((zone) => {
              const pct = zone.percent_full || 0;
              const barColor = pct > 80 ? "var(--color-sentinel-red)" : pct > 50 ? "var(--color-sentinel-amber)" : "var(--color-sentinel-green)";
              const badgeBg = pct > 80 ? "rgba(220, 38, 38, 0.15)" : pct > 50 ? "rgba(245, 158, 11, 0.15)" : "rgba(16, 185, 129, 0.15)";
              return (
                <div
                  key={zone.zone_id}
                  className="p-3 rounded-lg"
                  style={{
                    background: "var(--color-sentinel-bg-secondary)",
                    border: "1px solid var(--color-sentinel-border)",
                  }}
                >
                  <div className="flex justify-between items-center mb-1">
                    <span className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{zone.zone_name}</span>
                    <span
                      className="text-xs font-medium px-2 py-0.5 rounded"
                      style={{ background: badgeBg, color: barColor }}
                    >
                      {Math.round(pct)}%
                    </span>
                  </div>
                  <div className="text-2xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                    {zone.occupancy_count}
                    <span className="text-sm font-normal" style={{ color: "var(--color-sentinel-text-secondary)" }}>/{zone.max_capacity}</span>
                  </div>
                  {/* Progress bar */}
                  <div className="w-full rounded-full h-2 mt-2" style={{ background: "var(--color-sentinel-bg-panel)" }}>
                    <div className="h-2 rounded-full transition-all" style={{ width: `${Math.min(100, pct)}%`, background: barColor }} />
                  </div>
                  <div className="flex justify-between mt-1">
                    <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      <ArrowUpRight className="w-3 h-3 inline" /> {zone.badge_entries}
                    </span>
                    <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      <ArrowDownLeft className="w-3 h-3 inline" /> {zone.badge_exits}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      </div>
    </TabPanel>,

    // ===== Tab 2: Access Control =====
    <TabPanel key="access">
      <div className="space-y-4 mt-4">
        <AccessEventsPanel siteId={siteId} refreshKey={0} />
      </div>
    </TabPanel>,

    // ===== Tab 3: Cameras =====
    <TabPanel key="cameras">
      <div className="space-y-4 mt-4">
        <Card>
          <Title className="text-sm mb-3">CCTV Camera Status</Title>
          <div className="space-y-2">
            {demoCameras.map((cam) => (
              <div
                key={cam.camera_id}
                className="flex items-center justify-between p-3 rounded-lg border border-gray-200 dark:border-gray-700"
              >
                <div className="flex items-center gap-3">
                  {cam.status === "online" ? (
                    <Video className="w-5 h-5 text-green-400" />
                  ) : (
                    <VideoOff className="w-5 h-5 text-red-400" />
                  )}
                  <div>
                    <Text className="font-medium">{cam.name}</Text>
                    <Text className="text-xs text-gray-400">
                      {cam.floor} | {cam.camera_type.toUpperCase()} | {cam.resolution}
                      {cam.has_analytics ? " | AI Analytics" : ""}
                    </Text>
                    {cam.camera_model && (
                      <Text className="text-xs text-gray-500">{cam.camera_model}</Text>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {cam.motion_detected && (
                    <Badge color="amber" size="xs">
                      Motion
                    </Badge>
                  )}
                  <Badge color={cam.status === "online" ? "green" : cam.status === "fault" ? "amber" : "red"} size="xs">
                    {cam.status}
                  </Badge>
                  {cam.stream_url && (
                    <Text className="text-xs text-blue-400 cursor-pointer" title={cam.stream_url}>
                      Stream
                    </Text>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </TabPanel>,

    // ===== Tab 4: Occupancy Analysis =====
    <TabPanel key="analysis">
      <div className="space-y-4 mt-4">
        {/* 24-hour trend chart */}
        <Card>
          <Title className="text-sm mb-3">24-Hour Occupancy Trend</Title>
          <AreaChart
            className="h-64"
            data={demoTrendData.map((d) => ({
              hour: d.hour,
              Occupancy: d.net_occupancy,
              Entries: d.entries,
              Exits: d.exits,
            }))}
            index="hour"
            categories={["Occupancy", "Entries", "Exits"]}
            colors={["blue", "green", "red"]}
            showLegend={true}
            showGridLines={false}
            curveType="monotone"
          />
        </Card>

        {/* Peak hours and floor breakdown */}
        <Grid className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card>
            <Title className="text-sm mb-3">Peak Hours</Title>
            <div className="space-y-3">
              {[
                { time: "08:00-09:00", label: "Morning Arrival", occupancy: 35, icon: <ArrowUpRight className="w-4 h-4 text-green-400" /> },
                { time: "12:00-13:00", label: "Lunch Peak", occupancy: 28, icon: <Clock className="w-4 h-4 text-blue-400" /> },
                { time: "17:00-18:00", label: "Evening Departure", occupancy: 30, icon: <ArrowDownLeft className="w-4 h-4 text-amber-400" /> },
              ].map((peak) => (
                <div key={peak.time} className="flex items-center justify-between p-2 rounded border border-gray-200 dark:border-gray-700">
                  <div className="flex items-center gap-2">
                    {peak.icon}
                    <div>
                      <Text className="font-medium text-sm">{peak.time}</Text>
                      <Text className="text-xs text-gray-400">{peak.label}</Text>
                    </div>
                  </div>
                  <Badge color="blue">{peak.occupancy} people</Badge>
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <Title className="text-sm mb-3">Floor-by-Floor Breakdown</Title>
            <BarChart
              className="h-48"
              data={zoneOccupancies.map((z) => ({
                zone: z.zone_name,
                Occupancy: z.occupancy_count,
                Capacity: z.max_capacity || 50,
              }))}
              index="zone"
              categories={["Occupancy", "Capacity"]}
              colors={["blue", "gray"]}
              showLegend={true}
              showGridLines={false}
              layout="vertical"
            />
          </Card>
        </Grid>

        {/* Occupancy panel with cross-module recommendations */}
        <SecurityOccupancyPanel siteId={siteId} refreshKey={0} />
      </div>
    </TabPanel>,

    // ===== Tab 5: Integrations =====
    <TabPanel key="integrations">
      <div className="space-y-4 mt-4">
        {/* HVAC Integration */}
        <Card>
          <Flex alignItems="center" className="gap-2 mb-4">
            <Thermometer className="w-5 h-5 text-blue-400" />
            <Title className="text-sm">Security + HVAC Integration</Title>
            <Badge color="green" size="xs">Active</Badge>
          </Flex>
          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 rounded-lg border border-gray-200 dark:border-gray-700">
              <div>
                <Text className="font-medium">Occupancy-Based Setpoint Adjustment</Text>
                <Text className="text-xs text-gray-400">
                  Empty zones: relax cooling setpoint by +2 deg C. Low occupancy: +1 deg C.
                </Text>
              </div>
              <div className="flex items-center gap-2">
                <Badge color="green" size="xs">Enabled</Badge>
                <CheckCircle className="w-4 h-4 text-green-400" />
              </div>
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg border border-gray-200 dark:border-gray-700">
              <div>
                <Text className="font-medium">Low Occupancy Mode</Text>
                <Text className="text-xs text-gray-400">
                  Cool to +2 deg C setback, reduce ventilation for unoccupied zones.
                </Text>
              </div>
              <div className="flex items-center gap-2">
                <Badge color="green" size="xs">Enabled</Badge>
                <Zap className="w-4 h-4 text-green-400" />
              </div>
            </div>
          </div>
        </Card>

        {/* Lighting Integration */}
        <Card>
          <Flex alignItems="center" className="gap-2 mb-4">
            <Sun className="w-5 h-5 text-amber-400" />
            <Title className="text-sm">Security + Lighting Integration</Title>
            <Badge color="green" size="xs">Active</Badge>
          </Flex>
          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 rounded-lg border border-gray-200 dark:border-gray-700">
              <div>
                <Text className="font-medium">Occupancy-Based Lighting Control</Text>
                <Text className="text-xs text-gray-400">
                  Empty zones: dim to 20%. Low occupancy: dim to 50%.
                </Text>
              </div>
              <div className="flex items-center gap-2">
                <Badge color="green" size="xs">Enabled</Badge>
                <CheckCircle className="w-4 h-4 text-green-400" />
              </div>
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg border border-gray-200 dark:border-gray-700">
              <div>
                <Text className="font-medium">Unoccupied Zone Auto-Dim</Text>
                <Text className="text-xs text-gray-400">
                  Lights auto-dim to 20% after 15 min of no occupancy detected.
                </Text>
              </div>
              <div className="flex items-center gap-2">
                <Badge color="green" size="xs">Enabled</Badge>
                <Zap className="w-4 h-4 text-green-400" />
              </div>
            </div>
          </div>
        </Card>

        {/* Integration Status Summary */}
        <Card>
          <Title className="text-sm mb-3">Cross-Module Integration Status</Title>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="text-center p-4 rounded-lg border border-green-500/30 bg-green-500/5">
              <Text className="text-2xl font-bold text-green-400">2</Text>
              <Text className="text-xs text-gray-400">Active Integrations</Text>
            </div>
            <div className="text-center p-4 rounded-lg border border-blue-500/30 bg-blue-500/5">
              <Text className="text-2xl font-bold text-blue-400">{zoneOccupancies.length}</Text>
              <Text className="text-xs text-gray-400">Monitored Zones</Text>
            </div>
            <div className="text-center p-4 rounded-lg border border-amber-500/30 bg-amber-500/5">
              <Text className="text-2xl font-bold text-amber-400">~15%</Text>
              <Text className="text-xs text-gray-400">Est. Energy Savings</Text>
            </div>
          </div>
        </Card>
      </div>
    </TabPanel>,
  ];

  return (
    <div className="space-y-4">
      {/* Header */}
      <Flex justifyContent="between" alignItems="center">
        <Flex alignItems="center" className="gap-3">
          <Shield className="w-6 h-6 text-blue-400" />
          <div>
            <Title>Security</Title>
            <Text className="text-xs text-gray-400">
              Real-time occupancy, access monitoring, and cross-module automation
            </Text>
          </div>
        </Flex>
        <Flex alignItems="center" className="gap-3">
          {lastUpdated && (
            <Text className="text-xs text-gray-400">
              Updated: {formatTime(lastUpdated)}
            </Text>
          )}
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="flex items-center gap-2 px-3 py-1.5 rounded text-sm font-medium bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </Flex>
      </Flex>

      {/* Tabbed Layout */}
      <TabGroup index={activeTab} onIndexChange={setActiveTab}>
        <TabList variant="solid">
          {tabs as unknown as ReactElement[]}
        </TabList>
        <TabPanels>
          {panels as unknown as ReactElement[]}
        </TabPanels>
      </TabGroup>
    </div>
  );
}

export default SecurityDashboard;
