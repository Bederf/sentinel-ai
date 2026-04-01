/**
 * SENTINEL Building Intelligence Dashboard — Visual Preview
 *
 * Self-contained React component that renders a simulated Grafana dashboard
 * with live-updating mock data. Use for demos and stakeholder previews.
 *
 * Usage: Import into any React app with Tailwind CSS.
 *   import { GrafanaDashboardPreview } from './grafana-dashboard-preview';
 *   <GrafanaDashboardPreview />
 */

import React, { useState, useEffect, useCallback } from 'react';

// --- Types ---

interface AlertData {
  critical: number;
  warning: number;
  info: number;
}

interface EquipmentIssue {
  building: string;
  equipment: string;
  issue: string;
  severity: 'critical' | 'warning' | 'info';
  lastUpdated: string;
}

interface DegradingBuilding {
  name: string;
  count: number;
  color: string;
}

interface BacklogEntry {
  building: string;
  days: number;
}

interface ThroughputPoint {
  hour: string;
  value: number;
}

// --- Mock Data Generators ---

function randomBetween(min: number, max: number): number {
  return Math.round((Math.random() * (max - min) + min) * 10) / 10;
}

function generateAlerts(): AlertData {
  return {
    critical: Math.floor(Math.random() * 4),
    warning: Math.floor(Math.random() * 12) + 3,
    info: Math.floor(Math.random() * 20) + 8,
  };
}

function generateKPIs() {
  return {
    firstTimeFix: randomBetween(88, 99),
    slaAttainment: randomBetween(90, 99),
    avgResponseTime: randomBetween(120, 420), // seconds
  };
}

function generateIssues(): EquipmentIssue[] {
  const issues: EquipmentIssue[] = [
    { building: 'Sandton City Tower', equipment: 'S002-CHILLER-B1-001', issue: 'High discharge pressure', severity: 'critical', lastUpdated: '2 min ago' },
    { building: 'Rosebank Corner', equipment: 'S005-AHU-L2-003', issue: 'Fan belt vibration', severity: 'warning', lastUpdated: '15 min ago' },
    { building: 'Sandton City Tower', equipment: 'S002-FCU-205', issue: 'Valve actuator stuck', severity: 'warning', lastUpdated: '23 min ago' },
    { building: 'Durban Point', equipment: 'S008-GEN-B1-001', issue: 'Low fuel level', severity: 'warning', lastUpdated: '45 min ago' },
    { building: 'Cape Town Foreshore', equipment: 'S012-UPS-B1-001', issue: 'Battery cell imbalance', severity: 'critical', lastUpdated: '8 min ago' },
    { building: 'Pretoria Central', equipment: 'S003-DALI-L3-007', issue: 'Driver temperature high', severity: 'info', lastUpdated: '1 hr ago' },
    { building: 'Menlyn Maine', equipment: 'S007-VAV-301', issue: 'Damper position deviation', severity: 'info', lastUpdated: '2 hr ago' },
  ];
  return issues.slice(0, Math.floor(Math.random() * 3) + 5);
}

function generateDegrading(): DegradingBuilding[] {
  return [
    { name: 'Sandton City', count: Math.floor(Math.random() * 3) + 2, color: '#FF6384' },
    { name: 'Rosebank Corner', count: Math.floor(Math.random() * 2) + 1, color: '#36A2EB' },
    { name: 'Cape Town Foreshore', count: Math.floor(Math.random() * 3) + 1, color: '#FFCE56' },
    { name: 'Durban Point', count: Math.floor(Math.random() * 2), color: '#4BC0C0' },
    { name: 'Pretoria Central', count: Math.floor(Math.random() * 2), color: '#9966FF' },
  ].filter((b) => b.count > 0);
}

function generateBacklog(): BacklogEntry[] {
  return [
    { building: 'Sandton City', days: Math.floor(Math.random() * 15) + 5 },
    { building: 'Rosebank', days: Math.floor(Math.random() * 10) + 2 },
    { building: 'Cape Town', days: Math.floor(Math.random() * 12) + 3 },
    { building: 'Durban', days: Math.floor(Math.random() * 8) + 1 },
    { building: 'Pretoria', days: Math.floor(Math.random() * 6) + 1 },
    { building: 'Menlyn', days: Math.floor(Math.random() * 7) + 2 },
  ];
}

function generateThroughput(): ThroughputPoint[] {
  const points: ThroughputPoint[] = [];
  const now = new Date();
  for (let i = 23; i >= 0; i--) {
    const hour = new Date(now.getTime() - i * 3600000);
    const h = hour.getHours();
    // Higher throughput during business hours
    const base = h >= 7 && h <= 17 ? 12 : 3;
    points.push({
      hour: `${String(h).padStart(2, '0')}:00`,
      value: Math.max(0, base + Math.floor(Math.random() * 8) - 3),
    });
  }
  return points;
}

// --- Sub-components ---

function PanelCard({ title, children, className = '' }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-gray-900 border border-gray-700 rounded-lg overflow-hidden ${className}`}>
      <div className="px-4 py-2 border-b border-gray-700 bg-gray-800/50">
        <h3 className="text-sm font-medium text-gray-300">{title}</h3>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

function DonutChart({ data }: { data: AlertData }) {
  const total = data.critical + data.warning + data.info;
  if (total === 0) return <div className="text-gray-500 text-center py-8">No active alerts</div>;

  const segments = [
    { label: 'Critical', value: data.critical, color: '#EF4444', pct: ((data.critical / total) * 100).toFixed(0) },
    { label: 'Warning', value: data.warning, color: '#F97316', pct: ((data.warning / total) * 100).toFixed(0) },
    { label: 'Info', value: data.info, color: '#3B82F6', pct: ((data.info / total) * 100).toFixed(0) },
  ];

  return (
    <div className="flex items-center justify-between">
      <div className="relative w-32 h-32">
        <svg viewBox="0 0 36 36" className="w-full h-full">
          {(() => {
            let offset = 0;
            return segments.map((seg) => {
              const dash = (seg.value / total) * 100;
              const el = (
                <circle
                  key={seg.label}
                  cx="18" cy="18" r="14"
                  fill="none"
                  stroke={seg.color}
                  strokeWidth="4"
                  strokeDasharray={`${dash} ${100 - dash}`}
                  strokeDashoffset={-offset}
                  className="transition-all duration-500"
                />
              );
              offset += dash;
              return el;
            });
          })()}
          <text x="18" y="18" textAnchor="middle" dominantBaseline="central" className="fill-white text-[6px] font-bold">
            {total}
          </text>
        </svg>
      </div>
      <div className="space-y-2 ml-4">
        {segments.map((seg) => (
          <div key={seg.label} className="flex items-center gap-2 text-sm">
            <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: seg.color }} />
            <span className="text-gray-300">{seg.label}</span>
            <span className="text-white font-mono ml-auto">{seg.value}</span>
            <span className="text-gray-500 text-xs">({seg.pct}%)</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function GaugeDisplay({ value, label, unit = '%' }: { value: number; label: string; unit?: string }) {
  const color = value >= 95 ? '#22C55E' : value >= 80 ? '#EAB308' : '#EF4444';
  const angle = Math.min((value / 100) * 180, 180);

  return (
    <div className="flex flex-col items-center">
      <div className="relative w-28 h-16 overflow-hidden">
        <svg viewBox="0 0 120 70" className="w-full h-full">
          <path d="M 10 60 A 50 50 0 0 1 110 60" fill="none" stroke="#374151" strokeWidth="8" strokeLinecap="round" />
          <path
            d="M 10 60 A 50 50 0 0 1 110 60"
            fill="none"
            stroke={color}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={`${(angle / 180) * 157} 157`}
            className="transition-all duration-700"
          />
        </svg>
      </div>
      <div className="text-2xl font-bold mt-1" style={{ color }}>
        {value.toFixed(1)}{unit}
      </div>
      <div className="text-xs text-gray-400 mt-1">{label}</div>
    </div>
  );
}

function StatDisplay({ value, label, color, unit = '' }: { value: string | number; label: string; color: string; unit?: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-full py-4" style={{ backgroundColor: color + '20' }}>
      <div className="text-4xl font-bold" style={{ color }}>
        {value}{unit}
      </div>
      <div className="text-sm text-gray-400 mt-2">{label}</div>
    </div>
  );
}

function ThroughputChart({ data }: { data: ThroughputPoint[] }) {
  const max = Math.max(...data.map((d) => d.value), 1);

  return (
    <div className="flex items-end gap-[2px] h-32">
      {data.map((point, i) => (
        <div key={i} className="flex-1 flex flex-col items-center group relative">
          <div
            className="w-full bg-blue-500/60 hover:bg-blue-400/80 rounded-t-sm transition-all duration-300 min-h-[2px]"
            style={{ height: `${(point.value / max) * 100}%` }}
          />
          {i % 4 === 0 && <span className="text-[9px] text-gray-500 mt-1">{point.hour}</span>}
          <div className="absolute -top-6 bg-gray-800 text-white text-xs px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
            {point.value}/hr
          </div>
        </div>
      ))}
    </div>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const colors: Record<string, string> = {
    critical: 'bg-red-600 text-white',
    warning: 'bg-orange-500 text-white',
    info: 'bg-blue-600 text-white',
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[severity] || 'bg-gray-600 text-white'}`}>
      {severity}
    </span>
  );
}

function MiniPieChart({ data }: { data: DegradingBuilding[] }) {
  const total = data.reduce((sum, d) => sum + d.count, 0);
  if (total === 0) return <div className="text-gray-500 text-center py-4">No degrading equipment</div>;

  return (
    <div className="flex items-center justify-between">
      <div className="w-28 h-28">
        <svg viewBox="0 0 36 36">
          {(() => {
            let offset = 0;
            return data.map((seg) => {
              const dash = (seg.count / total) * 100;
              const el = (
                <circle key={seg.name} cx="18" cy="18" r="16" fill="none" stroke={seg.color} strokeWidth="6"
                  strokeDasharray={`${dash} ${100 - dash}`} strokeDashoffset={-offset} />
              );
              offset += dash;
              return el;
            });
          })()}
        </svg>
      </div>
      <div className="space-y-1.5 ml-4 flex-1">
        {data.map((b) => (
          <div key={b.name} className="flex items-center gap-2 text-xs">
            <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: b.color }} />
            <span className="text-gray-300 truncate">{b.name}</span>
            <span className="text-white font-mono ml-auto">{b.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function BacklogBars({ data }: { data: BacklogEntry[] }) {
  const max = Math.max(...data.map((d) => d.days), 1);
  const colors = ['#EF4444', '#F97316', '#EAB308', '#22C55E', '#3B82F6', '#8B5CF6'];

  return (
    <div className="space-y-2">
      {data.map((entry, i) => (
        <div key={entry.building} className="flex items-center gap-3">
          <span className="text-xs text-gray-400 w-20 truncate">{entry.building}</span>
          <div className="flex-1 bg-gray-800 rounded-full h-4 overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${(entry.days / max) * 100}%`, backgroundColor: colors[i % colors.length] }}
            />
          </div>
          <span className="text-xs text-white font-mono w-8 text-right">{entry.days}d</span>
        </div>
      ))}
    </div>
  );
}

// --- Main Dashboard Component ---

export function GrafanaDashboardPreview() {
  const [alerts, setAlerts] = useState<AlertData>(generateAlerts());
  const [kpis, setKpis] = useState(generateKPIs());
  const [issues, setIssues] = useState<EquipmentIssue[]>(generateIssues());
  const [degrading, setDegrading] = useState<DegradingBuilding[]>(generateDegrading());
  const [backlog, setBacklog] = useState<BacklogEntry[]>(generateBacklog());
  const [throughput, setThroughput] = useState<ThroughputPoint[]>(generateThroughput());
  const [lastUpdate, setLastUpdate] = useState(new Date());

  const refresh = useCallback(() => {
    setAlerts(generateAlerts());
    setKpis(generateKPIs());
    setIssues(generateIssues());
    setDegrading(generateDegrading());
    setBacklog(generateBacklog());
    setThroughput(generateThroughput());
    setLastUpdate(new Date());
  }, []);

  useEffect(() => {
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [refresh]);

  const formatResponseTime = (seconds: number): string => {
    const min = Math.floor(seconds / 60);
    const sec = Math.round(seconds % 60);
    return `${min}m ${sec}s`;
  };

  const responseColor = kpis.avgResponseTime < 300 ? '#22C55E' : kpis.avgResponseTime < 600 ? '#EAB308' : '#EF4444';

  return (
    <div className="min-h-screen bg-gray-950 text-white p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 px-2">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center font-bold text-sm">S</div>
          <div>
            <h1 className="text-lg font-semibold text-white">SENTINEL Building Intelligence</h1>
            <p className="text-xs text-gray-500">Media Wall Dashboard</p>
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs text-gray-500">
          <span>Building: <span className="text-gray-300">All</span></span>
          <span>Range: <span className="text-gray-300">Last 24h</span></span>
          <span>Refresh: <span className="text-green-400">10s</span></span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
            {lastUpdate.toLocaleTimeString()}
          </span>
        </div>
      </div>

      {/* Row 1: Alerts */}
      <div className="grid grid-cols-2 gap-3 mb-3">
        <PanelCard title="Active Alerts by Severity">
          <DonutChart data={alerts} />
        </PanelCard>
        <PanelCard title="Critical Alerts">
          <StatDisplay
            value={alerts.critical}
            label="Critical Alerts Active"
            color={alerts.critical > 0 ? '#EF4444' : '#22C55E'}
          />
        </PanelCard>
      </div>

      {/* Row 2: KPI Gauges */}
      <div className="grid grid-cols-3 gap-3 mb-3">
        <PanelCard title="First-Time Fix Rate">
          <GaugeDisplay value={kpis.firstTimeFix} label="Target: 95%" />
        </PanelCard>
        <PanelCard title="SLA Attainment">
          <GaugeDisplay value={kpis.slaAttainment} label="Target: 95%" />
        </PanelCard>
        <PanelCard title="Avg Critical Response Time">
          <StatDisplay
            value={formatResponseTime(kpis.avgResponseTime)}
            label="Target: < 5 min"
            color={responseColor}
          />
        </PanelCard>
      </div>

      {/* Row 3: Throughput */}
      <div className="mb-3">
        <PanelCard title="Job Card Throughput Trend (24h)">
          <ThroughputChart data={throughput} />
        </PanelCard>
      </div>

      {/* Row 4: Equipment Issues Table */}
      <div className="mb-3">
        <PanelCard title="Active Equipment Issues by Building">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-700">
                  <th className="pb-2 pr-4">Building</th>
                  <th className="pb-2 pr-4">Equipment</th>
                  <th className="pb-2 pr-4">Issue</th>
                  <th className="pb-2 pr-4">Severity</th>
                  <th className="pb-2">Last Updated</th>
                </tr>
              </thead>
              <tbody>
                {issues.map((issue, i) => (
                  <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50 transition-colors">
                    <td className="py-2 pr-4 text-gray-300">{issue.building}</td>
                    <td className="py-2 pr-4 font-mono text-xs text-gray-400">{issue.equipment}</td>
                    <td className="py-2 pr-4 text-white">{issue.issue}</td>
                    <td className="py-2 pr-4"><SeverityBadge severity={issue.severity} /></td>
                    <td className="py-2 text-gray-500 text-xs">{issue.lastUpdated}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </PanelCard>
      </div>

      {/* Row 5: Degrading + Backlog */}
      <div className="grid grid-cols-2 gap-3">
        <PanelCard title="Degrading Equipment by Building">
          <MiniPieChart data={degrading} />
        </PanelCard>
        <PanelCard title="Maintenance Backlog (Days) by Building">
          <BacklogBars data={backlog} />
        </PanelCard>
      </div>

      {/* Footer */}
      <div className="text-center text-xs text-gray-600 mt-4">
        SENTINEL Building Intelligence v43.0 — Simulated Preview (data refreshes every 5s)
      </div>
    </div>
  );
}

export default GrafanaDashboardPreview;
