/**
 * EnergyComparisonPanel Component - Wardew Tridonic Demo Card
 *
 * Shows 3-tier energy savings comparison driven by the DALI simulation engine:
 * 1. Baseline: Traditional lighting (100%)
 * 2. With DALI: Occupancy + daylight harvesting (Tridonic)
 * 3. With SENTINEL: AI optimization on top
 *
 * Data updates as the 365-day simulation progresses.
 * Used on dashboard as toggleable card. Part of Grant demo workflow.
 */

import { useState, useEffect, useCallback } from 'react';
import { Zap, TrendingDown, Leaf } from 'lucide-react';
import { authorizedFetch } from '@/lib/api';
import { useSimulation } from '@/contexts/SimulationContext';

interface Scenario {
  name: string;
  kwh: number;
  description: string;
  savings_percent: number;
  savings_kwh?: number;
}

export function EnergyComparisonPanel({ siteId }: { siteId: string }) {
  const [scenarios, setScenarios] = useState<Scenario[] | null>(null);
  const [periodDays, setPeriodDays] = useState(0);
  const [loading, setLoading] = useState(true);
  const { daysSimulated } = useSimulation();

  const fetchData = useCallback(async () => {
    try {
      const maxDay = Math.max(1, daysSimulated || 1);
      const response = await authorizedFetch(`/api/dali/simulation?site_id=${siteId}&max_day=${maxDay}`);
      const json = await response.json();
      const s = json.summary;

      // Convert cumulative ZAR costs to kWh (R5/kWh rate)
      const rate = 5;
      const baselineKwh = Math.round(s.baseline_annual_cost / rate);
      const daliKwh = Math.round(s.dali_annual_cost / rate);
      const sentinelKwh = Math.round(s.sentinel_annual_cost / rate);

      const daliSavingsPct = baselineKwh > 0 ? Math.round((1 - daliKwh / baselineKwh) * 100) : 0;
      const sentinelSavingsPct = baselineKwh > 0 ? Math.round((1 - sentinelKwh / baselineKwh) * 100) : 0;

      setScenarios([
        {
          name: "Baseline (No DALI)",
          kwh: baselineKwh,
          description: "Traditional lighting controls",
          savings_percent: 0,
        },
        {
          name: "With DALI (Tridonic)",
          kwh: daliKwh,
          description: "Occupancy & daylight harvesting",
          savings_percent: daliSavingsPct,
          savings_kwh: baselineKwh - daliKwh,
        },
        {
          name: "With SENTINEL (AI)",
          kwh: sentinelKwh,
          description: "AI optimization on top of DALI",
          savings_percent: sentinelSavingsPct,
          savings_kwh: baselineKwh - sentinelKwh,
        },
      ]);
      setPeriodDays(s.days_simulated || maxDay);
    } catch (error) {
      console.error('Failed to load comparison:', error);
    } finally {
      setLoading(false);
    }
  }, [siteId, daysSimulated]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) return <div className="p-4">Loading...</div>;
  if (!scenarios?.length) return null;

  const [baseline, withDali, withSentinel] = scenarios;

  return (
    <div
      className="rounded-md overflow-hidden"
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
      {/* Header */}
      <div
        className="p-4 flex items-center justify-between"
        style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
      >
        <div className="flex items-center gap-3">
          <div className="p-2 rounded" style={{ background: "rgba(34, 197, 94, 0.15)" }}>
            <Leaf className="h-5 w-5" style={{ color: "#22C55E" }} />
          </div>
          <div>
            <h3 className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
              Energy Impact: Wardew Tridonic Integration
            </h3>
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {periodDays > 0 ? `${periodDays}-day` : 'Cumulative'} consumption comparison (kWh)
            </span>
          </div>
        </div>
        <span className="text-xs px-2 py-1 rounded" style={{
          background: "rgba(34, 197, 94, 0.15)",
          color: "#22C55E"
        }}>
          {withSentinel.savings_percent}% Total Savings
        </span>
      </div>

      {/* 3-Bar Comparison */}
      <div className="p-4 space-y-4">
        <ScenarioBar
          scenario={baseline}
          color="gray"
          icon={<Zap className="h-4 w-4" />}
          percentage={100}
        />
        <ScenarioBar
          scenario={withDali}
          color="amber"
          icon={<TrendingDown className="h-4 w-4" />}
          percentage={(withDali.kwh / baseline.kwh) * 100}
          showSavings
        />
        <ScenarioBar
          scenario={withSentinel}
          color="green"
          icon={<Leaf className="h-4 w-4" />}
          percentage={(withSentinel.kwh / baseline.kwh) * 100}
          showSavings
        />

        {/* Value Proposition Callout */}
        <div className="mt-4 p-3 rounded-lg" style={{
          background: "rgba(34, 197, 94, 0.1)",
          border: "1px solid rgba(34, 197, 94, 0.3)"
        }}>
          <div className="flex items-center gap-2">
            <Leaf className="h-5 w-5" style={{ color: "#22C55E" }} />
            <div>
              <p className="text-sm font-medium" style={{ color: "#22C55E" }}>
                Wardew Tridonic + SENTINEL AI
              </p>
              <p className="text-xs" style={{ color: "rgba(34, 197, 94, 0.8)" }}>
                {(withSentinel.savings_kwh || 0).toLocaleString()} kWh saved &bull;
                R {((withSentinel.savings_kwh || 0) * 5).toLocaleString()} cost reduction
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Scenario Bar Component
function ScenarioBar({ scenario, color, icon, percentage, showSavings }: {
  scenario: Scenario;
  color: 'gray' | 'amber' | 'green';
  icon: React.ReactNode;
  percentage: number;
  showSavings?: boolean;
}) {
  const colorMap = {
    gray: '#6B7280',
    amber: '#F59E0B',
    green: '#22C55E',
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div style={{ color: colorMap[color] }}>{icon}</div>
          <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
            {scenario.name}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>
            {scenario.kwh.toLocaleString()} kWh
          </span>
          {showSavings && (
            <span className="text-xs px-2 py-1 rounded" style={{
              background: `rgba(${color === 'amber' ? '245, 158, 11' : '34, 197, 94'}, 0.15)`,
              color: colorMap[color]
            }}>
              -{scenario.savings_percent}%
            </span>
          )}
        </div>
      </div>

      {/* Progress Bar */}
      <div className="h-3 rounded-full overflow-hidden" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
        <div
          className="h-full transition-all duration-500"
          style={{
            width: `${percentage}%`,
            background: colorMap[color]
          }}
        />
      </div>

      <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
        {scenario.description}
      </p>
    </div>
  );
}
