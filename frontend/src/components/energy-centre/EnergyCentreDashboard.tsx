/**
 * Energy Centre Dashboard - Bolt-on Module
 *
 * Complete energy centre monitoring view combining:
 * - Single-line diagram
 * - Generator synoptic
 * - Power metering
 * - UPS status
 * - ATS status
 * - AI recommendations integration
 */

import { useState, useEffect, useCallback } from 'react';

import { Activity } from 'lucide-react';
import { TabBar } from '../TabBar';
import { PageLoading } from '../PageLoading';
import { energyCentreApi } from '../../lib/energyCentreApi';
import type { SCADAOverview } from '../../lib/energyCentreApi';
import { fetchEnergyComparisonSummary } from '../../lib/api/energy';
import { authorizedFetch } from '../../lib/api/client';
import { SingleLineDiagram } from './SingleLineDiagram';
import { GeneratorSynoptic } from './GeneratorSynoptic';
import { PowerMeteringCard } from './PowerMeteringCard';
import { UPSStatusPanel } from './UPSStatusPanel';
import { ATSStatusPanel } from './ATSStatusPanel';

interface EnergyCentreDashboardProps {
  siteId: string;
  onAIRecommendation?: (recommendation: AIRecommendation) => void;
  enabledModules?: string[];
}

interface AIRecommendation {
  id: string;
  type: 'energy' | 'hvac' | 'security' | 'cross_system';
  priority: 'low' | 'medium' | 'high' | 'critical';
  title: string;
  description: string;
  source_module: string;
  related_modules?: string[];
  action?: {
    type: string;
    target: string;
    value: any;
  };
  timestamp: string;
}

interface BridgeTelemetrySummary {
  status: 'live' | 'unavailable';
  zones_with_readings?: number;
  zone_count?: number;
  power?: {
    hvac_kw?: number;
    lighting_kw?: number;
    total_kw?: number;
  };
}

interface SentinelEnergySummary {
  savings_percent: number;
  daily_savings_zar: number;
  actual_kwh: number;
  sentinel_kwh: number;
}

export function EnergyCentreDashboard({ siteId, onAIRecommendation, enabledModules = ['energy'] }: EnergyCentreDashboardProps) {
  const [overview, setOverview] = useState<SCADAOverview | null>(null);
  const [alerts, setAlerts] = useState<AIRecommendation[]>([]);
  const [bridgeTelemetry, setBridgeTelemetry] = useState<BridgeTelemetrySummary | null>(null);
  const [sentinelEnergy, setSentinelEnergy] = useState<SentinelEnergySummary | null>(null);
  const [sentinelGuidance, setSentinelGuidance] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("overview");
  const TABS = [
    { id: "overview", label: "Overview" },
    { id: "generators", label: "Generators" },
    { id: "power", label: "Power" },
    { id: "ups", label: "UPS" },
  ] as const;

  const loadOverview = useCallback(async () => {
    try {
      const [data, comparison, rawTelemetryResp, stateResp] = await Promise.all([
        energyCentreApi.getSCADAOverview(siteId),
        fetchEnergyComparisonSummary(siteId).catch(() => null),
        authorizedFetch(`/api/sites/${encodeURIComponent(siteId)}/telemetry`).catch(() => null),
        authorizedFetch(`/api/building-state/${encodeURIComponent(siteId)}`).catch(() => null),
      ]);
      setOverview(data);

      // Generate AI recommendations based on telemetry
      const recommendations = generateRecommendations(data, enabledModules);
      setAlerts(recommendations);

      if (comparison) {
        setSentinelEnergy({
          savings_percent: comparison.daily_savings_percent,
          daily_savings_zar: comparison.daily_savings_zar,
          actual_kwh: comparison.actual.total_kwh,
          sentinel_kwh: comparison.sentinel.total_kwh,
        });
      } else {
        setSentinelEnergy(null);
      }

      if (rawTelemetryResp && rawTelemetryResp.ok) {
        const raw = await rawTelemetryResp.json();
        setBridgeTelemetry({
          status: 'live',
          zones_with_readings: raw?.zones_with_readings ?? 0,
          zone_count: raw?.zone_count ?? 0,
          power: raw?.power ?? {},
        });
      } else {
        setBridgeTelemetry({ status: 'unavailable' });
      }

      if (stateResp && stateResp.ok) {
        const state = await stateResp.json();
        setSentinelGuidance(state?.payload?.operator_guidance?.headline || null);
      } else {
        setSentinelGuidance(null);
      }

      // Notify parent of new recommendations
      if (onAIRecommendation && recommendations.length > 0) {
        recommendations.forEach(rec => onAIRecommendation(rec));
      }

      setLoading(false);
    } catch (_err) {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId]);

  useEffect(() => {
    loadOverview();
    const interval = setInterval(loadOverview, 10000);
    return () => clearInterval(interval);
  }, [loadOverview]);

  // AI-driven recommendation generation based on telemetry
  const generateRecommendations = useCallback((data: SCADAOverview, modules: string[]): AIRecommendation[] => {
    const recs: AIRecommendation[] = [];
    const now = new Date().toISOString();

    // Power factor recommendation
    if (data.power_metering.power_factor < 0.92) {
      recs.push({
        id: `pf-${Date.now()}`,
        type: 'energy',
        priority: data.power_metering.power_factor < 0.85 ? 'high' : 'medium',
        title: 'Low Power Factor',
        description: `Power factor at ${data.power_metering.power_factor.toFixed(2)} is below target 0.95. Consider increasing PFC compensation.`,
        source_module: 'energy',
        timestamp: now,
      });
    }

    // UPS battery warning
    if (data.ups.systems.some(s => s.battery_charge_pct < 80)) {
      const lowUPS = data.ups.systems.filter(s => s.battery_charge_pct < 80);
      recs.push({
        id: `ups-bat-${Date.now()}`,
        type: 'energy',
        priority: lowUPS.some(s => s.battery_charge_pct < 50) ? 'critical' : 'medium',
        title: 'UPS Battery Warning',
        description: `${lowUPS.length} UPS system(s) have low battery charge. Check battery health.`,
        source_module: 'energy',
        timestamp: now,
      });
    }

    // Generator fuel warning
    const fuelData = data.generators?.groups?.[0]?.fuel;
    if (fuelData && fuelData.current_level_pct < 30) {
      recs.push({
        id: `fuel-${Date.now()}`,
        type: 'energy',
        priority: fuelData.current_level_pct < 20 ? 'high' : 'medium',
        title: 'Low Fuel Level',
        description: `Diesel tank at ${fuelData.current_level_pct}%. Schedule fuel delivery.`,
        source_module: 'energy',
        timestamp: now,
      });
    }

    // Cross-system recommendation (Energy + HVAC)
    if (modules.includes('hvac') && !data.status.mains_healthy) {
      recs.push({
        id: `cross-hvac-${Date.now()}`,
        type: 'cross_system',
        priority: 'high',
        title: 'Load Shedding - HVAC Optimization',
        description: 'Mains power unavailable. Recommend reducing HVAC load to extend generator runtime.',
        source_module: 'energy',
        related_modules: ['hvac'],
        action: {
          type: 'setpoint_adjust',
          target: 'all_ahu',
          value: { temp_offset: 2 },
        },
        timestamp: now,
      });
    }

    // Transformer overload warning
    if (data.transformers.avg_load_percent > 80) {
      recs.push({
        id: `tx-load-${Date.now()}`,
        type: 'energy',
        priority: data.transformers.avg_load_percent > 90 ? 'critical' : 'high',
        title: 'High Transformer Load',
        description: `Transformers at ${data.transformers.avg_load_percent.toFixed(0)}% average load. Consider load balancing.`,
        source_module: 'energy',
        timestamp: now,
      });
    }

    return recs;
  }, []);

  if (loading) {
    return <PageLoading message="Loading energy centre..." />;
  }

  if (!overview) {
    return (
      <div className="h-full p-4 md:p-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 rounded" style={{ background: "rgba(234, 179, 8, 0.15)" }}>
            <Activity className="h-6 w-6" style={{ color: "var(--color-sentinel-amber)" }} />
          </div>
          <div>
            <h1 className="text-2xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>Energy Centre</h1>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Power Distribution & Generation Management</p>
          </div>
        </div>
        <Text className="text-red-500">Failed to load energy centre data</Text>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-4 md:p-6">
      {/* Page Header — matches Lighting tab pattern */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(234, 179, 8, 0.15)" }}>
              <Activity className="h-6 w-6" style={{ color: "var(--color-sentinel-amber)" }} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  Energy Centre
                </h1>
                {overview.status.on_generator ? (
                  <div className="px-2 py-0.5 rounded text-xs font-medium"
                    style={{ background: 'rgba(245, 158, 11, 0.15)', color: 'var(--color-sentinel-amber)' }}>
                    On Generator
                  </div>
                ) : (
                  <div className="px-2 py-0.5 rounded text-xs font-medium"
                    style={{ background: 'rgba(34, 197, 94, 0.15)', color: 'var(--color-sentinel-green)' }}>
                    Mains Supply
                  </div>
                )}
              </div>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Power Distribution & Generation Management
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="space-y-4">
      {/* AI Alerts Card */}
      <Card>

        {/* AI Alerts */}
        {alerts.length > 0 && (
          <div className="mt-4 pt-4 border-t border-gray-200">
            <Text className="text-sm font-bold mb-2">AI Recommendations</Text>
            <div className="space-y-2">
              {alerts.slice(0, 3).map(alert => (
                <div
                  key={alert.id}
                  className={`p-2 rounded-lg ${
                    alert.priority === 'critical' ? 'bg-red-50 border border-red-200' :
                    alert.priority === 'high' ? 'bg-amber-50 border border-amber-200' :
                    'bg-blue-50 border border-blue-200'
                  }`}
                >
                  <Flex justifyContent="between">
                    <Text className="font-medium">{alert.title}</Text>
                    <Badge color={
                      alert.priority === 'critical' ? 'red' :
                      alert.priority === 'high' ? 'amber' : 'blue'
                    }>
                      {alert.type === 'cross_system' ? 'Cross-System' : 'Energy'}
                    </Badge>
                  </Flex>
                  <Text className="text-xs mt-1">{alert.description}</Text>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>

      <TabBar
        tabs={TABS.map(t => ({ id: t.id, label: t.label }))}
        active={activeTab}
        onChange={setActiveTab}
        accentColor="var(--color-sentinel-blue)"
      />

      <div className="space-y-4">
        {activeTab === "overview" && (
          <>
          <div className="space-y-4 mb-4">
            <Card>
              <Flex justifyContent="between" alignItems="start">
                <div>
                  <Text className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                    Raw Bridge Telemetry
                  </Text>
                  <Text className="mt-1 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Zones: {bridgeTelemetry?.zones_with_readings ?? 0}/{bridgeTelemetry?.zone_count ?? 0} ·
                    HVAC: {(bridgeTelemetry?.power?.hvac_kw ?? 0).toFixed(2)} kW ·
                    Total: {(bridgeTelemetry?.power?.total_kw ?? 0).toFixed(2)} kW
                  </Text>
                </div>
                <Badge color={bridgeTelemetry?.status === 'live' ? 'green' : 'amber'}>
                  {bridgeTelemetry?.status === 'live' ? 'Live' : 'Unavailable'}
                </Badge>
              </Flex>
            </Card>

            <Card>
              <Text className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                SENTINEL Energy Intelligence
              </Text>
              <Text className="mt-1 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {sentinelEnergy
                  ? `Savings ${sentinelEnergy.savings_percent.toFixed(1)}% · Baseline ${sentinelEnergy.actual_kwh.toFixed(1)} kWh · With SENTINEL ${sentinelEnergy.sentinel_kwh.toFixed(1)} kWh`
                  : 'Energy comparison not available yet'}
              </Text>
              <Text className="mt-1 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {sentinelGuidance || 'No active guidance yet.'}
              </Text>
            </Card>
          </div>
          <Grid className="grid grid-cols-2 gap-4">
            <SingleLineDiagram siteId={siteId} />
            <div className="space-y-4">
              <ATSStatusPanel siteId={siteId} compact />
              <PowerMeteringCard siteId={siteId} compact />
              <UPSStatusPanel siteId={siteId} compact />
            </div>
          </Grid>
        </>
        )}

        {activeTab === "generators" && (
          <GeneratorSynoptic
            siteId={siteId}
            onHealthAlert={(gen, health) => {
              if (onAIRecommendation) {
                onAIRecommendation({
                  id: `gen-health-${gen.generator_id}`,
                  type: 'energy',
                  priority: health.status === 'critical' ? 'critical' : 'high',
                  title: `Generator ${gen.name} Health Alert`,
                  description: `Health score: ${health.overall_score.toFixed(0)}%. ${health.indicators.find(i => i.recommendation)?.recommendation || 'Check generator health.'}`,
                  source_module: 'energy',
                  timestamp: new Date().toISOString(),
                });
              }
            }}
          />
        )}

        {activeTab === "power" && (
          <PowerMeteringCard siteId={siteId} />
        )}

        {activeTab === "ups" && (
          <UPSStatusPanel
            siteId={siteId}
            onBatteryAlert={(ups) => {
              if (onAIRecommendation) {
                onAIRecommendation({
                  id: `ups-battery-${ups.ups_id}`,
                  type: 'energy',
                  priority: 'critical',
                  title: 'UPS On Battery',
                  description: `${ups.name} is running on battery. Runtime: ${ups.runtime_min.toFixed(0)} minutes.`,
                  source_module: 'energy',
                  timestamp: new Date().toISOString(),
                });
              }
            }}
          />
        )}
      </div>
      </div>
    </div>
  );
}

export default EnergyCentreDashboard;
