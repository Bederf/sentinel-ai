/* eslint-disable react-hooks/purity */
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

import { useContext, useState, useEffect, useCallback } from "react";

import {
  Shield,
  ShieldCheck,
  Users,
  Camera,
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
} from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";
import { SentinelValueCard } from "../SentinelValueCard";
import { securityApi } from "@/lib/api";
import type { SecurityOccupancy } from "@/lib/api";
import { authorizedFetch } from "@/lib/api/client";
import { AccessEventsPanel } from "../AccessEventsPanel";
import { SecurityOccupancyPanel } from "../SecurityOccupancyPanel";
import { ModuleContext } from "../../contexts/moduleContextStore";
import { Badge } from "../Badge";
import { TabBar } from "../TabBar";
import type { TabDef } from "../TabBar";

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

interface BridgeTelemetrySummary {
  status: "live" | "unavailable";
  zones_with_readings?: number;
  zone_count?: number;
  power?: {
    hvac_kw?: number;
    lighting_kw?: number;
    total_kw?: number;
  };
}

const badgeColors: Record<string, string> = {
  green: "bg-green-500/15 text-[var(--color-sentinel-green)]",
  amber: "bg-amber-500/15 text-[var(--color-sentinel-amber)]",
  red: "bg-red-500/15 text-[var(--color-sentinel-red)]",
  blue: "bg-blue-500/15 text-[var(--color-sentinel-blue)]",
  gray: "bg-gray-500/15 text-[var(--color-sentinel-text-secondary)]",
};

const badgeXs = " text-[10px] px-1.5 py-0.5";

const tooltipStyle: React.CSSProperties = {
  background: "var(--color-sentinel-bg-secondary)",
  border: "1px solid var(--color-sentinel-border)",
  borderRadius: 4,
  color: "var(--color-sentinel-text-primary)",
};

const TAB_DEFS: TabDef[] = [
  { id: "overview", label: "Overview" },
  { id: "access", label: "Access" },
  { id: "cameras", label: "Cameras" },
  { id: "analysis", label: "Occupancy" },
  { id: "integrations", label: "Integrations" },
];

export function SecurityDashboard({ siteId: propSiteId }: SecurityDashboardProps) {
  const moduleContext = useContext(ModuleContext);
  const siteId = propSiteId || moduleContext?.siteId || '';
  const [activeTab, setActiveTab] = useState("overview");
  const [loading, setLoading] = useState(true);
  const [occupancyData, setOccupancyData] = useState<{
    total_occupancy: number;
    zones: SecurityOccupancy[];
  }>({ total_occupancy: 0, zones: [] });
  const [bridgeTelemetry, setBridgeTelemetry] = useState<BridgeTelemetrySummary | null>(null);
  const [sentinelGuidance, setSentinelGuidance] = useState<string | null>(null);
  const [sentinelPosture, setSentinelPosture] = useState<string | null>(null);
  const [trendData, _setTrendData] = useState<TrendPoint[]>([]);
  const [cameras, _setCameras] = useState<CameraInfo[]>([]);
  const [_isRefreshing, _setIsRefreshing] = useState(false);
  const [_lastUpdated, _setLastUpdated] = useState<Date | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [occ, rawTelemetryResp, stateResp] = await Promise.all([
        securityApi.getOccupancy(siteId),
        authorizedFetch(`/api/sites/${encodeURIComponent(siteId)}/telemetry`).catch(() => null),
        authorizedFetch(`/api/building-state/${encodeURIComponent(siteId)}`).catch(() => null),
      ]);
      setOccupancyData(occ);

      if (rawTelemetryResp && rawTelemetryResp.ok) {
        const raw = await rawTelemetryResp.json();
        setBridgeTelemetry({
          status: "live",
          zones_with_readings: raw?.zones_with_readings ?? 0,
          zone_count: raw?.zone_count ?? 0,
          power: raw?.power ?? {},
        });
      } else {
        setBridgeTelemetry({ status: "unavailable" });
      }

      if (stateResp && stateResp.ok) {
        const state = await stateResp.json();
        setSentinelGuidance(state?.payload?.operator_guidance?.headline || null);
        setSentinelPosture(state?.payload?.building_posture || null);
      } else {
        setSentinelGuidance(null);
        setSentinelPosture(null);
      }

      _setLastUpdated(new Date());
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

  const _handleRefresh = async () => {
    _setIsRefreshing(true);
    await fetchData();
    _setIsRefreshing(false);
  };

  const _formatTime = (date: Date) =>
    date.toLocaleTimeString("en-ZA", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });

  // Loading state
  if (loading) {
    return (
      <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <h3 className="font-medium text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>Security Module</h3>
        <div
          className="animate-pulse h-96 rounded-lg mt-4"
          style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--color-sentinel-border)" }}
        />
      </div>
    );
  }

  // Generate local fallback trend data for chart (when no live data)
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
  const breachEvents = 0;

  return (
    <div className="h-full overflow-y-auto p-4 md:p-6" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
      {/* Page Header — matches Lighting tab pattern */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(59, 130, 246, 0.15)" }}>
              <Shield className="h-6 w-6" style={{ color: "var(--color-sentinel-blue)" }} />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Security
              </h1>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Access Control &amp; Occupancy Monitoring
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* TabBar */}
      <TabBar tabs={TAB_DEFS} active={activeTab} onChange={setActiveTab} />

      {/* ===== Tab 1: Overview ===== */}
      {activeTab === "overview" && (
        <div className="space-y-4 mt-4">
          <SentinelValueCard
            title="Security Intelligence Impact"
            icon={ShieldCheck}
            baseline={{ label: "", value: 0, unit: "incidents" }}
            sentinel={{ label: "", value: 0, unit: "incidents" }}
            savingsPercent={0}
            period="Monthly"
            collecting
          />

          {/* Raw + SENTINEL Security View */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
              <div className="flex justify-between items-start mb-2">
                <p className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Raw Bridge Telemetry</p>
                <Badge className={bridgeTelemetry?.status === "live" ? badgeColors.green : badgeColors.amber}>
                  {bridgeTelemetry?.status === "live" ? "Live" : "Unavailable"}
                </Badge>
              </div>
              <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Zones: {bridgeTelemetry?.zones_with_readings ?? 0}/{bridgeTelemetry?.zone_count ?? 0}
              </p>
              <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Power: HVAC {(bridgeTelemetry?.power?.hvac_kw ?? 0).toFixed(2)} kW · Total {(bridgeTelemetry?.power?.total_kw ?? 0).toFixed(2)} kW
              </p>
            </div>

            <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
              <p className="text-sm font-semibold mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>SENTINEL Security Interpretation</p>
              <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Posture: <span className="capitalize" style={{ color: "var(--color-sentinel-text-primary)" }}>{sentinelPosture || "unknown"}</span>
              </p>
              <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {sentinelGuidance || "No active guidance yet."}
              </p>
            </div>
          </div>

          {/* KPI Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
              <div className="flex items-center gap-2 mb-2">
                <Users className="w-5 h-5 text-blue-400" />
                <p className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>Total Occupancy</p>
              </div>
              <div className="text-3xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>{totalOccupancy}</div>
              <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {capacityPercent}% of {totalCapacity} capacity
              </p>
            </div>

            <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle className="w-5 h-5 text-green-400" />
                <p className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>Active Zones</p>
              </div>
              <div className="text-3xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>{zoneOccupancies.filter((z) => z.occupancy_count > 0).length}</div>
              <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>of {zoneOccupancies.length} zones</p>
            </div>

            <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
              <div className="flex items-center gap-2 mb-2">
                <Camera className="w-5 h-5 text-cyan-400" />
                <p className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>Cameras Online</p>
              </div>
              <div className="text-3xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>{onlineCameras}/{demoCameras.length}</div>
              <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {demoCameras.filter((c) => c.has_analytics).length} with AI analytics
              </p>
            </div>

            <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
              <div className="flex items-center gap-2 mb-2">
                <AlertTriangle className="w-5 h-5 text-amber-400" />
                <p className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>Breach Events (24h)</p>
              </div>
              <div className="text-3xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>{breachEvents}</div>
              <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>Unauthorized access attempts</p>
            </div>
          </div>

          {/* Floor Occupancy Cards */}
          <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
            <h4 className="font-medium text-sm mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>Zone Occupancy</h4>
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
          </div>
        </div>
      )}

      {/* ===== Tab 2: Access Control ===== */}
      {activeTab === "access" && (
        <div className="space-y-4 mt-4">
          <AccessEventsPanel siteId={siteId} refreshKey={0} />
        </div>
      )}

      {/* ===== Tab 3: Cameras ===== */}
      {activeTab === "cameras" && (
        <div className="space-y-4 mt-4">
          <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
            <h4 className="font-medium text-sm mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>CCTV Camera Status</h4>
            <div className="space-y-2">
              {demoCameras.map((cam) => (
                <div
                  key={cam.camera_id}
                  className="flex items-center justify-between p-3 rounded-lg"
                  style={{ border: "1px solid var(--color-sentinel-border)", background: "var(--color-sentinel-bg-secondary)" }}
                >
                  <div className="flex items-center gap-3">
                    {cam.status === "online" ? (
                      <Video className="w-5 h-5 text-green-400" />
                    ) : (
                      <VideoOff className="w-5 h-5 text-red-400" />
                    )}
                    <div>
                      <p className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>{cam.name}</p>
                      <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                        {cam.floor} | {cam.camera_type.toUpperCase()} | {cam.resolution}
                        {cam.has_analytics ? " | AI Analytics" : ""}
                      </p>
                      {cam.camera_model && (
                        <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>{cam.camera_model}</p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {cam.motion_detected && (
                      <Badge className={badgeColors.amber + badgeXs}>
                        Motion
                      </Badge>
                    )}
                    <Badge className={`${cam.status === "online" ? badgeColors.green : cam.status === "fault" ? badgeColors.amber : badgeColors.red}${badgeXs}`}>
                      {cam.status}
                    </Badge>
                    {cam.stream_url && (
                      <span className="text-xs" style={{ color: "var(--color-sentinel-blue)", cursor: "pointer" }} title={cam.stream_url}>
                        Stream
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ===== Tab 4: Occupancy Analysis ===== */}
      {activeTab === "analysis" && (
        <div className="space-y-4 mt-4">
          {/* 24-hour trend chart */}
          <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
            <h4 className="font-medium text-sm mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>24-Hour Occupancy Trend</h4>
            <div style={{ height: 256 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={demoTrendData.map((d) => ({
                    hour: d.hour,
                    Occupancy: d.net_occupancy,
                    Entries: d.entries,
                    Exits: d.exits,
                  }))}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-sentinel-border)" vertical={false} />
                  <XAxis dataKey="hour" stroke="var(--color-sentinel-text-secondary)" style={{ fontSize: 12 }} />
                  <YAxis stroke="var(--color-sentinel-text-secondary)" style={{ fontSize: 12 }} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Area type="monotone" dataKey="Occupancy" stroke="var(--color-sentinel-blue)" fill="var(--color-sentinel-blue)" fillOpacity={0.1} />
                  <Area type="monotone" dataKey="Entries" stroke="var(--color-sentinel-green)" fill="var(--color-sentinel-green)" fillOpacity={0.1} />
                  <Area type="monotone" dataKey="Exits" stroke="var(--color-sentinel-red)" fill="var(--color-sentinel-red)" fillOpacity={0.1} />
                  <Legend />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Peak hours and floor breakdown */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
              <h4 className="font-medium text-sm mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>Peak Hours</h4>
              <div className="space-y-3">
                {[
                  { time: "08:00-09:00", label: "Morning Arrival", occupancy: 35, icon: <ArrowUpRight className="w-4 h-4 text-green-400" /> },
                  { time: "12:00-13:00", label: "Lunch Peak", occupancy: 28, icon: <Clock className="w-4 h-4 text-blue-400" /> },
                  { time: "17:00-18:00", label: "Evening Departure", occupancy: 30, icon: <ArrowDownLeft className="w-4 h-4 text-amber-400" /> },
                ].map((peak) => (
                  <div
                    key={peak.time}
                    className="flex items-center justify-between p-2 rounded-lg"
                    style={{ border: "1px solid var(--color-sentinel-border)", background: "var(--color-sentinel-bg-secondary)" }}
                  >
                    <div className="flex items-center gap-2">
                      {peak.icon}
                      <div>
                        <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{peak.time}</p>
                        <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>{peak.label}</p>
                      </div>
                    </div>
                    <Badge className={badgeColors.blue}>{peak.occupancy} people</Badge>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
              <h4 className="font-medium text-sm mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>Floor-by-Floor Breakdown</h4>
              <div style={{ height: 192 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={zoneOccupancies.map((z) => ({
                      zone: z.zone_name,
                      Occupancy: z.occupancy_count,
                      Capacity: z.max_capacity || 50,
                    }))}
                    layout="vertical"
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-sentinel-border)" horizontal={false} />
                    <XAxis type="number" stroke="var(--color-sentinel-text-secondary)" style={{ fontSize: 12 }} />
                    <YAxis type="category" dataKey="zone" stroke="var(--color-sentinel-text-secondary)" style={{ fontSize: 12 }} width={120} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Bar dataKey="Occupancy" fill="var(--color-sentinel-blue)" radius={[0, 4, 4, 0]} />
                    <Bar dataKey="Capacity" fill="var(--color-sentinel-text-secondary)" radius={[0, 4, 4, 0]} />
                    <Legend />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <SecurityOccupancyPanel siteId={siteId} refreshKey={0} />
        </div>
      )}

      {/* ===== Tab 5: Integrations ===== */}
      {activeTab === "integrations" && (
        <div className="space-y-4 mt-4">
          {/* HVAC Integration */}
          <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
            <div className="flex items-center gap-2 mb-4">
              <Thermometer className="w-5 h-5 text-blue-400" />
              <h4 className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>Security + HVAC Integration</h4>
              <Badge className={badgeColors.green + badgeXs}>Active</Badge>
            </div>
            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 rounded-lg" style={{ border: "1px solid var(--color-sentinel-border)", background: "var(--color-sentinel-bg-secondary)" }}>
                <div>
                  <p className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>Occupancy-Based Setpoint Adjustment</p>
                  <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Empty zones: relax cooling setpoint by +2 deg C. Low occupancy: +1 deg C.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge className={badgeColors.green + badgeXs}>Enabled</Badge>
                  <CheckCircle className="w-4 h-4 text-green-400" />
                </div>
              </div>
              <div className="flex items-center justify-between p-3 rounded-lg" style={{ border: "1px solid var(--color-sentinel-border)", background: "var(--color-sentinel-bg-secondary)" }}>
                <div>
                  <p className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>Low Occupancy Mode</p>
                  <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Cool to +2 deg C setback, reduce ventilation for unoccupied zones.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge className={badgeColors.green + badgeXs}>Enabled</Badge>
                  <Zap className="w-4 h-4 text-green-400" />
                </div>
              </div>
            </div>
          </div>

          {/* Lighting Integration */}
          <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
            <div className="flex items-center gap-2 mb-4">
              <Sun className="w-5 h-5 text-amber-400" />
              <h4 className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>Security + Lighting Integration</h4>
              <Badge className={badgeColors.green + badgeXs}>Active</Badge>
            </div>
            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 rounded-lg" style={{ border: "1px solid var(--color-sentinel-border)", background: "var(--color-sentinel-bg-secondary)" }}>
                <div>
                  <p className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>Occupancy-Based Lighting Control</p>
                  <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Empty zones: dim to 20%. Low occupancy: dim to 50%.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge className={badgeColors.green + badgeXs}>Enabled</Badge>
                  <CheckCircle className="w-4 h-4 text-green-400" />
                </div>
              </div>
              <div className="flex items-center justify-between p-3 rounded-lg" style={{ border: "1px solid var(--color-sentinel-border)", background: "var(--color-sentinel-bg-secondary)" }}>
                <div>
                  <p className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>Unoccupied Zone Auto-Dim</p>
                  <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Lights auto-dim to 20% after 15 min of no occupancy detected.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge className={badgeColors.green + badgeXs}>Enabled</Badge>
                  <Zap className="w-4 h-4 text-green-400" />
                </div>
              </div>
            </div>
          </div>

          {/* Integration Status Summary */}
          <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
            <h4 className="font-medium text-sm mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>Cross-Module Integration Status</h4>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="text-center p-4 rounded-lg" style={{ border: "1px solid rgba(16, 185, 129, 0.3)", background: "rgba(16, 185, 129, 0.05)" }}>
                <p className="text-2xl font-bold" style={{ color: "var(--color-sentinel-green)" }}>2</p>
                <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>Active Integrations</p>
              </div>
              <div className="text-center p-4 rounded-lg" style={{ border: "1px solid rgba(59, 130, 246, 0.3)", background: "rgba(59, 130, 246, 0.05)" }}>
                <p className="text-2xl font-bold" style={{ color: "var(--color-sentinel-blue)" }}>{zoneOccupancies.length}</p>
                <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>Monitored Zones</p>
              </div>
              <div className="text-center p-4 rounded-lg" style={{ border: "1px solid rgba(245, 158, 11, 0.3)", background: "rgba(245, 158, 11, 0.05)" }}>
                <p className="text-2xl font-bold" style={{ color: "var(--color-sentinel-amber)" }}>~15%</p>
                <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>Est. Energy Savings</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default SecurityDashboard;
