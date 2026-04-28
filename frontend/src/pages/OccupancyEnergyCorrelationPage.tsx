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
import { Card } from '@/components/Card';
import { authorizedFetch } from '@/lib/api/client';

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

export function OccupancyEnergyCorrelationPage() {
  const [correlationData, setCorrelationData] = useState<CorrelationResponse | null>(null);
  const [scenariosData, setScenariosData] = useState<ScenariosResponse | null>(null);
  const [savingsData, setSavingsData] = useState<SavingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [corrRes, scenRes, savRes] = await Promise.all([
          authorizedFetch('/api/occupancy-energy/correlation?site_id=bld-002'),
          authorizedFetch('/api/occupancy-energy/scenarios?site_id=bld-002'),
          authorizedFetch('/api/occupancy-energy/savings-potential?site_id=bld-002'),
        ]);

        if (!corrRes.ok || !scenRes.ok || !savRes.ok) {
          throw new Error('Failed to fetch occupancy-energy correlation data');
        }

        const [corr, scen, sav] = await Promise.all([
          corrRes.json(),
          scenRes.json(),
          savRes.json(),
        ]);

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
  }, []);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <div className="w-8 h-8 border-4 border-gray-400 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-gray-400">Loading occupancy-energy analysis...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center text-red-400">
          <AlertCircle className="w-8 h-8 mx-auto mb-3" />
          <p>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-4 md:p-6 space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-100 mb-2">Occupancy-Energy Correlation</h1>
        <p className="text-gray-400">Analyze how occupancy patterns impact energy consumption and identify cost-saving opportunities</p>
      </div>

      {/* Daily Summary Cards */}
      {correlationData && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card>
            <div className="p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-gray-400 text-sm">Wasted Energy</span>
                <TrendingDown className="w-4 h-4 text-red-400" />
              </div>
              <div className="text-2xl font-bold text-gray-100">{correlationData.daily_summary.total_wasted_kwh} kWh</div>
              <p className="text-xs text-gray-500 mt-1">Today's excess consumption</p>
            </div>
          </Card>

          <Card>
            <div className="p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-gray-400 text-sm">Cost of Waste</span>
                <DollarSign className="w-4 h-4 text-orange-400" />
              </div>
              <div className="text-2xl font-bold text-gray-100">R{correlationData.daily_summary.total_cost_wasted_r.toFixed(2)}</div>
              <p className="text-xs text-gray-500 mt-1">Today's wasted cost</p>
            </div>
          </Card>

          <Card>
            <div className="p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-gray-400 text-sm">Carbon Waste</span>
                <Leaf className="w-4 h-4 text-green-400" />
              </div>
              <div className="text-2xl font-bold text-gray-100">{correlationData.daily_summary.total_carbon_wasted_kg.toFixed(1)} kg CO₂</div>
              <p className="text-xs text-gray-500 mt-1">Today's excess emissions</p>
            </div>
          </Card>

          <Card>
            <div className="p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-gray-400 text-sm">Peak Waste Hour</span>
                <AlertCircle className="w-4 h-4 text-yellow-400" />
              </div>
              <div className="text-2xl font-bold text-gray-100">{String(correlationData.daily_summary.peak_waste_hour).padStart(2, '0')}:00</div>
              <p className="text-xs text-gray-500 mt-1">{correlationData.daily_summary.peak_waste_kwh.toFixed(1)} kWh wasted</p>
            </div>
          </Card>
        </div>
      )}

      {/* Occupancy vs Energy Correlation Chart */}
      {correlationData && (
        <Card>
          <div className="p-6 border-b border-gray-700">
            <h2 className="text-lg font-semibold text-gray-100 mb-2">Occupancy vs Energy Consumption</h2>
            <p className="text-sm text-gray-400">Actual energy should correlate with occupancy. Gap between actual and optimal shows waste.</p>
          </div>
          <div className="p-6">
            <ResponsiveContainer width="100%" height={400}>
              <LineChart data={correlationData.hourly_data}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-sentinel-border)" />
                <XAxis dataKey="time" stroke="var(--color-sentinel-text-secondary)" />
                <YAxis yAxisId="left" stroke="var(--color-sentinel-blue)" unit="%" />
                <YAxis yAxisId="right" orientation="right" stroke="var(--color-sentinel-red)" unit=" kWh" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'var(--color-sentinel-bg-secondary)',
                    border: '1px solid var(--color-sentinel-border)',
                    borderRadius: '4px',
                  }}
                  formatter={(value: any) => typeof value === 'number' ? value.toFixed(2) : value}
                />
                <Legend />
                <Line type="monotone" dataKey="occupancy_percent" stroke="var(--color-sentinel-blue)" name="Occupancy %" yAxisId="left" />
                <Line type="monotone" dataKey="actual_kwh" stroke="var(--color-sentinel-red)" name="Actual Energy" yAxisId="right" />
                <Line type="monotone" dataKey="optimal_kwh" stroke="var(--color-sentinel-green)" name="Optimal Energy" yAxisId="right" strokeDasharray="5 5" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      {/* "Lights Left On" Scenarios */}
      {scenariosData && (
        <div>
          <h2 className="text-lg font-semibold text-gray-100 mb-4">Cost Impact of Common Scenarios</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {scenariosData.scenarios.map((scenario, idx) => (
              <Card key={idx}>
                <div className="p-6">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h3 className="font-semibold text-gray-100">{scenario.name}</h3>
                      <p className="text-xs text-gray-400 mt-1">{scenario.description}</p>
                    </div>
                    {scenario.icon === 'check-circle' && <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0" />}
                    {scenario.icon === 'lightbulb' && <Lightbulb className="w-5 h-5 text-yellow-400 flex-shrink-0" />}
                    {scenario.icon === 'alert-circle' && <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />}
                  </div>

                  <div className="space-y-3 mt-4">
                    <div>
                      <div className="flex justify-between mb-1">
                        <span className="text-xs text-gray-400">Daily Cost</span>
                        <span className="text-sm font-semibold text-gray-100">R{scenario.daily_cost_r.toFixed(2)}</span>
                      </div>
                      <div className="text-xs text-gray-500">
                        Excess: <span className="text-orange-400">R{scenario.excess_cost_r.toFixed(2)}</span>
                      </div>
                    </div>

                    <div>
                      <div className="flex justify-between mb-1">
                        <span className="text-xs text-gray-400">Daily Carbon</span>
                        <span className="text-sm font-semibold text-gray-100">{scenario.daily_carbon_kg.toFixed(1)} kg</span>
                      </div>
                      <div className="text-xs text-gray-500">
                        Excess: <span className="text-green-400">{scenario.excess_carbon_kg.toFixed(1)} kg CO₂</span>
                      </div>
                    </div>

                    <div className="pt-2 border-t border-gray-700">
                      <p className="text-xs text-gray-400">Probability: <span className="text-gray-300">{scenario.probability}</span></p>
                    </div>
                  </div>
                </div>
              </Card>
            ))}
          </div>

          {scenariosData.annual_impact && (
            <Card className="mt-4">
              <div className="p-6">
                <h3 className="font-semibold text-gray-100 mb-4">Annual Impact Projections</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <p className="text-xs text-gray-400 mb-1">Worst Case (24/7 on)</p>
                    <p className="text-lg font-bold text-gray-100">R{scenariosData.annual_impact.worst_case_cost_r.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 mb-1">Common Case (After hours)</p>
                    <p className="text-lg font-bold text-gray-100">R{scenariosData.annual_impact.common_case_cost_r.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 mb-1">Optimal (Scaled)</p>
                    <p className="text-lg font-bold text-green-400">R{scenariosData.annual_impact.optimal_cost_r.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 mb-1">Potential Savings</p>
                    <p className="text-lg font-bold text-green-400">+R{scenariosData.annual_impact.annual_savings_common_r.toLocaleString()}</p>
                  </div>
                </div>
              </div>
            </Card>
          )}
        </div>
      )}

      {/* Savings Potential Breakdown */}
      {savingsData && (
        <div>
          <h2 className="text-lg font-semibold text-gray-100 mb-4">Energy Savings Potential</h2>

          {/* Current vs Optimized Comparison */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <Card>
              <div className="p-6">
                <h3 className="font-semibold text-gray-100 mb-4">Current Baseline</h3>
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-gray-400">HVAC</span>
                    <span className="font-semibold text-gray-100">{savingsData.baseline.hvac_kwh} kWh</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Lighting</span>
                    <span className="font-semibold text-gray-100">{savingsData.baseline.lighting_kwh} kWh</span>
                  </div>
                  <div className="border-t border-gray-700 pt-3 flex justify-between">
                    <span className="text-gray-400">Total Daily Cost</span>
                    <span className="font-semibold text-gray-100">R{savingsData.baseline.cost_r.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Carbon Footprint</span>
                    <span className="font-semibold text-gray-100">{savingsData.baseline.carbon_kg.toFixed(1)} kg</span>
                  </div>
                </div>
              </div>
            </Card>

            <Card>
              <div className="p-6">
                <h3 className="font-semibold text-gray-100 mb-4">With Optimizations</h3>
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-gray-400">HVAC (Setback)</span>
                    <span className="font-semibold text-green-400">{savingsData.optimized_state.hvac_kwh} kWh</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Lighting</span>
                    <span className="font-semibold text-green-400">{savingsData.optimized_state.lighting_kwh} kWh</span>
                  </div>
                  <div className="border-t border-gray-700 pt-3 flex justify-between">
                    <span className="text-gray-400">Total Daily Cost</span>
                    <span className="font-semibold text-green-400">R{savingsData.optimized_state.cost_r.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Carbon Footprint</span>
                    <span className="font-semibold text-green-400">{savingsData.optimized_state.carbon_kg.toFixed(1)} kg</span>
                  </div>
                </div>
              </div>
            </Card>
          </div>

          {/* Optimization Details */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {savingsData.optimizations.map((opt, idx) => (
              <Card key={idx}>
                <div className="p-6">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h3 className="font-semibold text-gray-100">{opt.name}</h3>
                      <p className="text-xs text-gray-400 mt-1">{opt.description}</p>
                    </div>
                    {idx === 0 ? <Wind className="w-5 h-5 text-blue-400 flex-shrink-0" /> : <Lightbulb className="w-5 h-5 text-yellow-400 flex-shrink-0" />}
                  </div>

                  <div className="space-y-2 mt-4 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-400">Savings</span>
                      <span className="font-semibold text-green-400">{opt.savings_kwh} kWh/day</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Cost Reduction</span>
                      <span className="font-semibold text-green-400">R{opt.savings_cost_r.toFixed(2)}/day</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Carbon Reduction</span>
                      <span className="font-semibold text-green-400">{opt.savings_carbon_kg.toFixed(2)} kg/day</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">% of Total Energy</span>
                      <span className="font-semibold text-blue-400">{opt.savings_percent}%</span>
                    </div>
                    <div className="border-t border-gray-700 pt-2 flex justify-between">
                      <span className="text-gray-400">ROI</span>
                      <span className="font-semibold text-gray-100">{opt.roi_months} months</span>
                    </div>
                  </div>

                  <p className="text-xs text-gray-500 mt-3 border-t border-gray-700 pt-3">
                    <span className="text-gray-400">Implementation:</span> {opt.implementation}
                  </p>
                </div>
              </Card>
            ))}
          </div>

          {/* Combined Savings Summary */}
          <Card className="mt-4">
            <div className="p-6">
              <h3 className="font-semibold text-gray-100 mb-4">Combined Savings Potential</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-xs text-gray-400 mb-2">Daily Savings</p>
                  <p className="text-xl font-bold text-green-400">{savingsData.combined.total_savings_kwh} kWh</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400 mb-2">Cost Savings/Day</p>
                  <p className="text-xl font-bold text-green-400">R{savingsData.combined.total_savings_cost_r.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400 mb-2">Carbon Reduction/Day</p>
                  <p className="text-xl font-bold text-green-400">{savingsData.combined.total_savings_carbon_kg.toFixed(1)} kg</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400 mb-2">% Reduction</p>
                  <p className="text-xl font-bold text-green-400">{savingsData.combined.savings_percent}%</p>
                </div>
              </div>

              <div className="border-t border-gray-700 mt-4 pt-4">
                <h4 className="font-semibold text-gray-100 mb-3">Annual Projections</h4>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
                  <div>
                    <p className="text-gray-400 mb-1">Current Annual Cost</p>
                    <p className="text-lg font-bold text-gray-100">R{savingsData.annual_projections.baseline_cost_r.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-gray-400 mb-1">Optimized Annual Cost</p>
                    <p className="text-lg font-bold text-green-400">R{savingsData.annual_projections.optimized_cost_r.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-gray-400 mb-1">Annual Savings</p>
                    <p className="text-lg font-bold text-green-400">+R{savingsData.annual_projections.annual_savings_r.toLocaleString()}</p>
                  </div>
                </div>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* Recommendations */}
      <Card>
        <div className="p-6 border-b border-gray-700">
          <h2 className="text-lg font-semibold text-gray-100">Implementation Recommendations</h2>
        </div>
        <div className="p-6 space-y-4">
          <div className="flex gap-3">
            <Wind className="w-5 h-5 text-blue-400 flex-shrink-0 mt-1" />
            <div>
              <h3 className="font-semibold text-gray-100">HVAC Setback Control</h3>
              <p className="text-sm text-gray-400 mt-1">Install smart thermostats with occupancy sensors. Automatically reduce HVAC load when occupancy drops below 30%. ROI: 18 months.</p>
            </div>
          </div>

          <div className="flex gap-3">
            <Lightbulb className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-1" />
            <div>
              <h3 className="font-semibold text-gray-100">Daylight Harvesting</h3>
              <p className="text-sm text-gray-400 mt-1">Enable daylight harvesting on lighting ballasts when natural light is sufficient. Reduces artificial lighting by 5%. ROI: 12 months.</p>
            </div>
          </div>

          <div className="flex gap-3">
            <AlertCircle className="w-5 h-5 text-orange-400 flex-shrink-0 mt-1" />
            <div>
              <h3 className="font-semibold text-gray-100">Occupancy Awareness</h3>
              <p className="text-sm text-gray-400 mt-1">Educate staff about "lights left on" costs. Peak waste occurs at 5-7pm during departures. A single forgotten light zone costs ~R5/day.</p>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}

export default OccupancyEnergyCorrelationPage;
