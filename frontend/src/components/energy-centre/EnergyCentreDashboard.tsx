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
import { Card, Title, Text, Grid, Badge, Flex, Tab, TabGroup, TabList, TabPanel, TabPanels } from '@tremor/react';
import { energyCentreApi } from '../../lib/energyCentreApi';
import type { SCADAOverview } from '../../lib/energyCentreApi';
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

export function EnergyCentreDashboard({ siteId, onAIRecommendation, enabledModules = ['energy'] }: EnergyCentreDashboardProps) {
  const [overview, setOverview] = useState<SCADAOverview | null>(null);
  const [alerts, setAlerts] = useState<AIRecommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState(0);

  const loadOverview = useCallback(async () => {
    try {
      const data = await energyCentreApi.getSCADAOverview(siteId);
      setOverview(data);

      // Generate AI recommendations based on telemetry
      const recommendations = generateRecommendations(data, enabledModules);
      setAlerts(recommendations);

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
    return (
      <Card>
        <Title>Energy Centre</Title>
        <div className="animate-pulse h-96 bg-gray-100 rounded mt-4" />
      </Card>
    );
  }

  if (!overview) {
    return (
      <Card>
        <Title>Energy Centre</Title>
        <Text className="text-red-500">Failed to load energy centre data</Text>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header with Status */}
      <Card>
        <Flex justifyContent="between" alignItems="center">
          <div>
            <Title>Energy Centre - {overview.centre?.name || siteId}</Title>
            <Text className="text-xs">Last update: {new Date(overview.timestamp).toLocaleTimeString()}</Text>
          </div>
          <div className="flex gap-2">
            {overview.status.on_generator ? (
              <Badge color="amber" size="lg">ON GENERATOR</Badge>
            ) : (
              <Badge color="green" size="lg">MAINS SUPPLY</Badge>
            )}
            <Badge color={overview.status.all_systems_normal ? 'green' : 'amber'}>
              {overview.status.all_systems_normal ? 'Normal' : 'Attention'}
            </Badge>
          </div>
        </Flex>

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

      {/* Tabbed Views */}
      <TabGroup index={activeTab} onIndexChange={setActiveTab}>
        <TabList className="mb-4">
          <Tab>Overview</Tab>
          <Tab>Generators</Tab>
          <Tab>Power</Tab>
          <Tab>UPS</Tab>
        </TabList>

        <TabPanels>
          {/* Overview Tab */}
          <TabPanel>
            <Grid numItems={2} className="gap-4">
              <SingleLineDiagram siteId={siteId} />
              <div className="space-y-4">
                <ATSStatusPanel siteId={siteId} compact />
                <PowerMeteringCard siteId={siteId} compact />
                <UPSStatusPanel siteId={siteId} compact />
              </div>
            </Grid>
          </TabPanel>

          {/* Generators Tab */}
          <TabPanel>
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
          </TabPanel>

          {/* Power Tab */}
          <TabPanel>
            <PowerMeteringCard siteId={siteId} />
          </TabPanel>

          {/* UPS Tab */}
          <TabPanel>
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
          </TabPanel>
        </TabPanels>
      </TabGroup>
    </div>
  );
}

export default EnergyCentreDashboard;
