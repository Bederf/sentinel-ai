/**
 * Occupancy-Energy Correlation Analysis Page
 *
 * Shows how occupancy patterns impact energy consumption and cost.
 * Features:
 * - Time-series correlation chart (occupancy vs actual vs optimal energy)
 * - "Lights Left On" cost impact scenarios
 * - HVAC/Lighting savings potential breakdown
 * - Annual projection of savings
 */

import { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { AlertCircle, CheckCircle, Lightbulb, Wind, TrendingDown, DollarSign, Leaf } from 'lucide-react';
import { Panel } from '@/components/Panel';
import { KPICard } from '@/components/KPICard';
import { authorizedFetch } from '@/lib/api/client';
import { PageLoading } from '@/components/PageLoading';

interface CorrelationDataPoint {
  hour: number;
  time: string;
  occupancy_percent: number;
  actual_kwh: number;
  optimal_kwh: number;
  wasted_kwh: number;
  cost_waste_r: number;
  carbon_waste_kg: number;
}

interface CorrelationResponse {
  date: string;
  site_id: string;
  hourly_data: CorrelationDataPoint[];
  daily_summary: {
    total_wasted_kwh: number;
    total_cost_wasted_r: number;
    total_carbon_wasted_kg: number;
    peak_waste_hour: number;
    peak_waste_kwh: number;
  };
}

interface Scenario {
  name: string;
  description: string;
  daily_cost_r: number;
  daily_carbon_kg: number;
  excess_cost_r: number;
  excess_carbon_kg: number;
  probability: string;
  icon: string;
}

interface ScenariosResponse {
  date: string;
  site_id: string;
  scenarios: Scenario[];
  annual_impact: {
    worst_case_cost_r: number;
    common_case_cost_r: number;
    optimal_cost_r: number;
    annual_savings_worst_r: number;
    annual_savings_common_r: number;
  };
}

interface Optimization {
  name: string;
  description: string;
  savings_kwh: number;
  savings_cost_r: number;
  savings_carbon_kg: number;
  savings_percent: number;
  cost_per_kwh_saved_r: number;
  implementation: string;
  roi_months: number;
}

interface SavingsResponse {
  date: string;
  site_id: string;
  baseline: {
    hvac_kwh: number;
    lighting_kwh: number;
    total_kwh: number;
    cost_r: number;
    carbon_kg: number;
  };
  optimizations: Optimization[];
  combined: {
    total_savings_kwh: number;
    total_savings_cost_r: number;
    total_savings_carbon_kg: number;
    savings_percent: number;
  };
  optimized_state: {
    hvac_kwh: number;
    lighting_kwh: number;
    total_kwh: number;
    cost_r: number;
    carbon_kg: number;
  };
  annual_projections: {
    baseline_cost_r: number;
    optimized_cost_r: number;
    annual_savings_r: number;
    annual_carbon_reduction_kg: number;
  };
}

const T = {
  primary:    "var(--color-sentinel-text-primary)",
  secondary:  "var(--color-sentinel-text-secondary)",
  disabled:   "var(--color-sentinel-text-disabled)",
  border:     "var(--color-sentinel-border)",
  bgSecondary:"var(--color-sentinel-bg-secondary)",
  green:      "var(--color-sentinel-green)",
  red:        "var(--color-sentinel-red)",
  amber:      "var(--color-sentinel-amber)",
  blue:       "var(--color-sentinel-blue)",
};

function DataRow({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-sm" style={{ color: T.secondary }}>{label}</span>
      <span className="text-sm font-semibold tabular-nums" style={{ color: valueColor ?? T.primary }}>{value}</span>
    </div>
  );
}

interface OccupancyEnergyCorrelationPageProps {
  siteId?: string;
}

export function OccupancyEnergyCorrelationPage({ siteId: propSiteId }: OccupancyEnergyCorrelationPageProps) {
  const [correlationData, setCorrelationData] = useState<CorrelationResponse | null>(null);
  const [scenariosData, setScenariosData] = useState<ScenariosResponse | null>(null);
  const [savingsData, setSavingsData] = useState<SavingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const siteId = propSiteId || 'bld-002';

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [corrRes, scenRes, savRes] = await Promise.all([
          authorizedFetch(`/api/occupancy-energy/correlation?site_id=${encodeURIComponent(siteId)}`),
          authorizedFetch(`/api/occupancy-energy/scenarios?site_id=${encodeURIComponent(siteId)}`),
          authorizedFetch(`/api/occupancy-energy/savings-potential?site_id=${encodeURIComponent(siteId)}`),
        ]);

        if (!corrRes.ok || !scenRes.ok || !savRes.ok) {
          throw new Error('Failed to fetch occupancy-energy correlation data');
        }

        const [corr, scen, sav] = await Promise.all([corrRes.json(), scenRes.json(), savRes.json()]);
        setCorrelationData(corr);
        setScenariosData(scen);
        setSavingsData(sav);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [siteId]);

  return (
    <div className="h-full overflow-y-auto" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
      {loading ? (
        <PageLoading message="Loading occupancy-energy analysis…" />
      ) : error ? (
        <div className="h-full flex items-center justify-center">
          <div className="text-center">
            <AlertCircle className="w-8 h-8 mx-auto mb-3" style={{ color: T.red }} />
            <p className="text-sm" style={{ color: T.secondary }}>{error}</p>
          </div>
        </div>
      ) : (
        <div className="space-y-6 p-4 md:p-6">

          {/* Page header */}
          <div>
            <h1 className="text-xl font-semibold" style={{ color: T.primary }}>
              Occupancy-Energy Correlation
            </h1>
            <p className="text-sm mt-0.5" style={{ color: T.secondary }}>
              Analyze how occupancy patterns impact energy consumption and identify cost-saving opportunities.
            </p>
          </div>

          {/* Daily Summary KPIs */}
          {correlationData && (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <KPICard
                title="Wasted Energy"
                value={`${correlationData.daily_summary.total_wasted_kwh} kWh`}
                icon={<TrendingDown className="h-5 w-5" />}
                accentColor="red"
              />
              <KPICard
                title="Cost of Waste"
                value={`R${correlationData.daily_summary.total_cost_wasted_r.toFixed(2)}`}
                icon={<DollarSign className="h-5 w-5" />}
                accentColor="orange"
              />
              <KPICard
                title="Carbon Waste"
                value={`${correlationData.daily_summary.total_carbon_wasted_kg.toFixed(1)} kg CO₂`}
                icon={<Leaf className="h-5 w-5" />}
                accentColor="green"
              />
              <KPICard
                title="Peak Waste Hour"
                value={`${String(correlationData.daily_summary.peak_waste_hour).padStart(2, '0')}:00`}
                icon={<AlertCircle className="h-5 w-5" />}
                accentColor="orange"
                delta={correlationData.daily_summary.peak_waste_kwh}
                deltaText="kWh wasted"
              />
            </div>
          )}

          {/* Occupancy vs Energy Chart */}
          {correlationData && (
            <Panel
              header={{
                icon: <TrendingDown className="h-4 w-4" />,
                title: "Occupancy vs Energy Consumption",
                accentColor: T.blue,
              }}
            >
              <div className="p-4 pb-6">
                <p className="text-xs mb-4" style={{ color: T.secondary }}>
                  Actual energy should correlate with occupancy. Gap between actual and optimal shows waste.
                </p>
                <ResponsiveContainer width="100%" height={360}>
                  <LineChart data={correlationData.hourly_data}>
                    <CartesianGrid strokeDasharray="3 3" stroke={T.border} />
                    <XAxis dataKey="time" stroke={T.secondary} tick={{ fontSize: 11 }} />
                    <YAxis yAxisId="left" stroke={T.blue} unit="%" tick={{ fontSize: 11 }} />
                    <YAxis yAxisId="right" orientation="right" stroke={T.red} unit=" kWh" tick={{ fontSize: 11 }} />
                    <Tooltip
                      contentStyle={{ backgroundColor: "var(--color-sentinel-bg-secondary)", border: `1px solid ${T.border}`, borderRadius: 4 }}
                      formatter={(value) => typeof value === 'number' ? value.toFixed(2) : value}
                    />
                    <Legend />
                    <Line type="monotone" dataKey="occupancy_percent" stroke={T.blue} name="Occupancy %" yAxisId="left" dot={false} />
                    <Line type="monotone" dataKey="actual_kwh" stroke={T.red} name="Actual Energy" yAxisId="right" dot={false} />
                    <Line type="monotone" dataKey="optimal_kwh" stroke={T.green} name="Optimal Energy" yAxisId="right" strokeDasharray="5 5" dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Panel>
          )}

          {/* Cost Impact Scenarios */}
          {scenariosData && (
            <Panel
              header={{
                icon: <AlertCircle className="h-4 w-4" />,
                title: "Cost Impact of Common Scenarios",
                accentColor: T.amber,
              }}
            >
              <div className="p-4 grid grid-cols-1 md:grid-cols-3 gap-4">
                {scenariosData.scenarios.map((scenario, idx) => (
                  <div
                    key={idx}
                    className="rounded-lg p-4 space-y-3"
                    style={{ background: T.bgSecondary, border: `1px solid ${T.border}` }}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h3 className="text-sm font-medium" style={{ color: T.primary }}>{scenario.name}</h3>
                        <p className="text-xs mt-0.5" style={{ color: T.secondary }}>{scenario.description}</p>
                      </div>
                      {scenario.icon === 'check-circle' && <CheckCircle className="w-4 h-4 flex-shrink-0 mt-0.5" style={{ color: T.green }} />}
                      {scenario.icon === 'lightbulb' && <Lightbulb className="w-4 h-4 flex-shrink-0 mt-0.5" style={{ color: T.amber }} />}
                      {scenario.icon === 'alert-circle' && <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" style={{ color: T.red }} />}
                    </div>
                    <div className="space-y-1.5">
                      <div className="flex justify-between">
                        <span className="text-xs" style={{ color: T.secondary }}>Daily Cost</span>
                        <span className="text-xs font-semibold tabular-nums" style={{ color: T.primary }}>R{scenario.daily_cost_r.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-xs" style={{ color: T.secondary }}>Excess Cost</span>
                        <span className="text-xs tabular-nums" style={{ color: T.amber }}>R{scenario.excess_cost_r.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-xs" style={{ color: T.secondary }}>Carbon Excess</span>
                        <span className="text-xs tabular-nums" style={{ color: T.green }}>{scenario.excess_carbon_kg.toFixed(1)} kg CO₂</span>
                      </div>
                    </div>
                    <div className="pt-2" style={{ borderTop: `1px solid ${T.border}` }}>
                      <p className="text-xs" style={{ color: T.disabled }}>
                        Probability: <span style={{ color: T.secondary }}>{scenario.probability}</span>
                      </p>
                    </div>
                  </div>
                ))}
              </div>

              {scenariosData.annual_impact && (
                <div className="px-4 pb-4 pt-1">
                  <div
                    className="rounded-lg p-4"
                    style={{ background: T.bgSecondary, border: `1px solid ${T.border}` }}
                  >
                    <h3 className="text-xs font-medium mb-3" style={{ color: T.secondary }}>Annual Impact Projections</h3>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      {[
                        { label: "Worst Case (24/7)", value: `R${scenariosData.annual_impact.worst_case_cost_r.toLocaleString()}`, color: T.red },
                        { label: "Common Case", value: `R${scenariosData.annual_impact.common_case_cost_r.toLocaleString()}`, color: T.amber },
                        { label: "Optimal", value: `R${scenariosData.annual_impact.optimal_cost_r.toLocaleString()}`, color: T.green },
                        { label: "Potential Savings", value: `+R${scenariosData.annual_impact.annual_savings_common_r.toLocaleString()}`, color: T.green },
                      ].map(({ label, value, color }) => (
                        <div key={label}>
                          <p className="text-xs mb-1" style={{ color: T.disabled }}>{label}</p>
                          <p className="text-base font-bold tabular-nums" style={{ color }}>{value}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </Panel>
          )}

          {/* Savings Potential */}
          {savingsData && (
            <>
              {/* Current vs Optimized */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <Panel
                  header={{
                    icon: <DollarSign className="h-4 w-4" />,
                    title: "Current Baseline",
                    accentColor: T.red,
                  }}
                >
                  <div className="p-4 space-y-2">
                    <DataRow label="HVAC" value={`${savingsData.baseline.hvac_kwh} kWh`} />
                    <DataRow label="Lighting" value={`${savingsData.baseline.lighting_kwh} kWh`} />
                    <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 8 }}>
                      <DataRow label="Total Daily Cost" value={`R${savingsData.baseline.cost_r.toFixed(2)}`} />
                      <DataRow label="Carbon Footprint" value={`${savingsData.baseline.carbon_kg.toFixed(1)} kg`} />
                    </div>
                  </div>
                </Panel>

                <Panel
                  header={{
                    icon: <Leaf className="h-4 w-4" />,
                    title: "With Optimizations",
                    accentColor: T.green,
                  }}
                >
                  <div className="p-4 space-y-2">
                    <DataRow label="HVAC (Setback)" value={`${savingsData.optimized_state.hvac_kwh} kWh`} valueColor={T.green} />
                    <DataRow label="Lighting" value={`${savingsData.optimized_state.lighting_kwh} kWh`} valueColor={T.green} />
                    <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 8 }}>
                      <DataRow label="Total Daily Cost" value={`R${savingsData.optimized_state.cost_r.toFixed(2)}`} valueColor={T.green} />
                      <DataRow label="Carbon Footprint" value={`${savingsData.optimized_state.carbon_kg.toFixed(1)} kg`} valueColor={T.green} />
                    </div>
                  </div>
                </Panel>
              </div>

              {/* Optimization Opportunities */}
              <Panel
                header={{
                  icon: <TrendingDown className="h-4 w-4" />,
                  title: "Optimization Opportunities",
                  accentColor: T.blue,
                }}
              >
                <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                  {savingsData.optimizations.map((opt, idx) => (
                    <div
                      key={idx}
                      className="rounded-lg p-4 space-y-3"
                      style={{ background: T.bgSecondary, border: `1px solid ${T.border}` }}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <h3 className="text-sm font-medium" style={{ color: T.primary }}>{opt.name}</h3>
                          <p className="text-xs mt-0.5" style={{ color: T.secondary }}>{opt.description}</p>
                        </div>
                        {idx === 0
                          ? <Wind className="w-4 h-4 flex-shrink-0 mt-0.5" style={{ color: T.blue }} />
                          : <Lightbulb className="w-4 h-4 flex-shrink-0 mt-0.5" style={{ color: T.amber }} />}
                      </div>
                      <div className="space-y-1.5">
                        <DataRow label="Energy Savings" value={`${opt.savings_kwh} kWh/day`} valueColor={T.green} />
                        <DataRow label="Cost Reduction" value={`R${opt.savings_cost_r.toFixed(2)}/day`} valueColor={T.green} />
                        <DataRow label="Carbon Reduction" value={`${opt.savings_carbon_kg.toFixed(2)} kg/day`} valueColor={T.green} />
                        <DataRow label="% of Total Energy" value={`${opt.savings_percent}%`} valueColor={T.blue} />
                      </div>
                      <div className="pt-2 space-y-1.5" style={{ borderTop: `1px solid ${T.border}` }}>
                        <DataRow label="ROI" value={`${opt.roi_months} months`} />
                        <p className="text-xs" style={{ color: T.disabled }}>
                          <span style={{ color: T.secondary }}>Implementation:</span> {opt.implementation}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </Panel>

              {/* Combined Savings */}
              <Panel
                header={{
                  icon: <Leaf className="h-4 w-4" />,
                  title: "Combined Savings Potential",
                  accentColor: T.green,
                }}
              >
                <div className="p-4 space-y-4">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {[
                      { label: "Daily Savings", value: `${savingsData.combined.total_savings_kwh} kWh` },
                      { label: "Cost Savings/Day", value: `R${savingsData.combined.total_savings_cost_r.toFixed(2)}` },
                      { label: "Carbon/Day", value: `${savingsData.combined.total_savings_carbon_kg.toFixed(1)} kg` },
                      { label: "% Reduction", value: `${savingsData.combined.savings_percent}%` },
                    ].map(({ label, value }) => (
                      <div key={label}>
                        <p className="text-xs mb-1" style={{ color: T.secondary }}>{label}</p>
                        <p className="text-lg font-bold tabular-nums" style={{ color: T.green }}>{value}</p>
                      </div>
                    ))}
                  </div>

                  <div className="pt-4" style={{ borderTop: `1px solid ${T.border}` }}>
                    <p className="text-xs font-medium mb-3" style={{ color: T.secondary }}>Annual Projections</p>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                      <div>
                        <p className="text-xs mb-1" style={{ color: T.disabled }}>Current Annual Cost</p>
                        <p className="text-base font-bold tabular-nums" style={{ color: T.primary }}>
                          R{savingsData.annual_projections.baseline_cost_r.toLocaleString()}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs mb-1" style={{ color: T.disabled }}>Optimized Annual Cost</p>
                        <p className="text-base font-bold tabular-nums" style={{ color: T.green }}>
                          R{savingsData.annual_projections.optimized_cost_r.toLocaleString()}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs mb-1" style={{ color: T.disabled }}>Annual Savings</p>
                        <p className="text-base font-bold tabular-nums" style={{ color: T.green }}>
                          +R{savingsData.annual_projections.annual_savings_r.toLocaleString()}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </Panel>
            </>
          )}

          {/* Recommendations */}
          <Panel
            header={{
              icon: <AlertCircle className="h-4 w-4" />,
              title: "Implementation Recommendations",
              accentColor: T.blue,
            }}
          >
            <div className="p-4 space-y-4">
              {[
                {
                  icon: <Wind className="w-5 h-5 flex-shrink-0 mt-0.5" style={{ color: T.blue }} />,
                  title: "HVAC Setback Control",
                  body: "Install smart thermostats with occupancy sensors. Automatically reduce HVAC load when occupancy drops below 30%. ROI: 18 months.",
                },
                {
                  icon: <Lightbulb className="w-5 h-5 flex-shrink-0 mt-0.5" style={{ color: T.amber }} />,
                  title: "Daylight Harvesting",
                  body: "Enable daylight harvesting on lighting ballasts when natural light is sufficient. Reduces artificial lighting by 5%. ROI: 12 months.",
                },
                {
                  icon: <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" style={{ color: T.amber }} />,
                  title: "Occupancy Awareness",
                  body: 'Educate staff about "lights left on" costs. Peak waste occurs at 5–7pm during departures. A single forgotten light zone costs ~R5/day.',
                },
              ].map(({ icon, title, body }) => (
                <div key={title} className="flex gap-3">
                  {icon}
                  <div>
                    <h3 className="text-sm font-medium" style={{ color: T.primary }}>{title}</h3>
                    <p className="text-sm mt-1" style={{ color: T.secondary }}>{body}</p>
                  </div>
                </div>
              ))}
            </div>
          </Panel>

        </div>
      )}
    </div>
  );
}

export default OccupancyEnergyCorrelationPage;
