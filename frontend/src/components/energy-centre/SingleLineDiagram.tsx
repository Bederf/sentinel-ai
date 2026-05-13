/**
 * Single-Line Diagram (SLD) - Bolt-on Module
 *
 * Visual representation of electrical distribution:
 * - MV Incomer → Transformers → ATS → Generators → LV Distribution
 * - Real-time status colors
 * - Energized path highlighting
 */

import { useState, useEffect, useCallback } from 'react';
import { energyCentreApi } from '../../lib/energyCentreApi';
import type { SLDData, SLDNode } from '../../lib/energyCentreApi';

interface SingleLineDiagramProps {
  siteId: string;
  compact?: boolean;
}

const sentinelColors: Record<string, string> = {
  blue: 'var(--sentinel-blue)',
  amber: 'var(--sentinel-amber)',
  gray: 'var(--sentinel-text-disabled)',
  green: 'var(--sentinel-green)',
  red: 'var(--sentinel-red)',
  cyan: 'var(--sentinel-cyan)',
  purple: '#7c3aed',
  yellow: '#eab308',
  slate: '#64748b',
};

const nodeColors: Record<string, { bg: string; border: string; text: string }> = {
  healthy: { bg: 'bg-green-100', border: 'border-green-500', text: 'text-green-700' },
  running: { bg: 'bg-green-100', border: 'border-green-500', text: 'text-green-700' },
  online: { bg: 'bg-green-100', border: 'border-green-500', text: 'text-green-700' },
  closed: { bg: 'bg-green-100', border: 'border-green-500', text: 'text-green-700' },
  standby: { bg: 'bg-gray-100', border: 'border-gray-400', text: 'text-gray-600' },
  open: { bg: 'bg-gray-100', border: 'border-gray-400', text: 'text-gray-600' },
  fault: { bg: 'bg-red-100', border: 'border-red-500', text: 'text-red-700' },
  tripped: { bg: 'bg-red-100', border: 'border-red-500', text: 'text-red-700' },
  mains: { bg: 'bg-blue-100', border: 'border-blue-500', text: 'text-blue-700' },
  generator: { bg: 'bg-amber-100', border: 'border-amber-500', text: 'text-amber-700' },
  battery: { bg: 'bg-orange-100', border: 'border-orange-500', text: 'text-orange-700' },
};

function getNodeStyle(node: SLDNode) {
  const status = node.status || node.position || node.mode || node.breaker || 'standby';
  return nodeColors[status] || nodeColors.standby;
}

function NodeBox({ node, compact }: { node: SLDNode; compact: boolean }) {
  const style = getNodeStyle(node);

  return (
    <div
      className={`
        ${style.bg} ${style.border} border-2 rounded-lg p-2
        ${compact ? 'min-w-[80px]' : 'min-w-[120px]'}
        transition-all duration-300
      `}
    >
      <span className={`text-xs font-bold ${style.text}`}>{node.label}</span>
      {!compact && (
        <div className="mt-1">
          {node.voltage !== undefined && (
            <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>{node.voltage.toFixed(1)} {node.type === 'mv_incomer' ? 'kV' : 'V'}</span>
          )}
          {node.load_percent !== undefined && (
            <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>{node.load_percent}% load</span>
          )}
          {node.temp_c !== undefined && (
            <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>{node.temp_c}°C</span>
          )}
          {node.power_kw !== undefined && (
            <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>{node.power_kw.toFixed(0)} kW</span>
          )}
          {node.battery_pct !== undefined && (
            <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>Bat: {node.battery_pct}%</span>
          )}
          {node.position && (
            <span className="text-xs px-1 py-0.5 rounded font-medium" style={{ background: sentinelColors[node.position === 'mains' ? 'blue' : 'amber'], color: "white" }}>
              {node.position.toUpperCase()}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function ConnectionLine({ energized }: { energized: boolean }) {
  return (
    <div className={`
      h-1 w-8 mx-1
      ${energized ? 'bg-green-500' : 'bg-gray-300'}
      transition-colors duration-300
    `} />
  );
}

function VerticalLine({ energized }: { energized: boolean }) {
  return (
    <div className={`
      w-1 h-6
      ${energized ? 'bg-green-500' : 'bg-gray-300'}
      transition-colors duration-300
    `} />
  );
}

export function SingleLineDiagram({ siteId, compact = false }: SingleLineDiagramProps) {
  const [sldData, setSldData] = useState<SLDData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const data = await energyCentreApi.getSLDData(siteId);
      setSldData(data);
      setLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load SLD data');
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 3000);
    return () => clearInterval(interval);
  }, [loadData]);

  if (loading) {
    return (
      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Single-Line Diagram</h3>
        <div className="animate-pulse h-48 bg-gray-100 rounded mt-4" />
      </div>
    );
  }

  if (error || !sldData) {
    return (
      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Single-Line Diagram</h3>
        <span className="text-red-500">{error || 'No SLD data available'}</span>
      </div>
    );
  }

  // Organize nodes by type for rendering
  const mvIncomers = sldData.nodes.filter(n => n.type === 'mv_incomer');
  const transformers = sldData.nodes.filter(n => n.type === 'transformer');
  const atsUnits = sldData.nodes.filter(n => n.type === 'ats');
  const generators = sldData.nodes.filter(n => n.type === 'generator');
  const switchboards = sldData.nodes.filter(n => n.type === 'switchboard');
  const upsUnits = sldData.nodes.filter(n => n.type === 'ups');

  // Check if path is energized
  const isMainsEnergized = sldData.status.mains_healthy && !sldData.status.on_generator;
  const isGenEnergized = sldData.status.on_generator;

  return (
    <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Single-Line Diagram</h3>
        <div className="flex gap-2">
          <span className="text-xs px-2 py-0.5 rounded font-medium" style={{ background: sentinelColors[sldData.status.mains_healthy ? 'green' : 'red'], color: "white" }}>
            Mains {sldData.status.mains_healthy ? 'OK' : 'FAIL'}
          </span>
          {sldData.status.on_generator && (
            <span className="text-xs px-2 py-0.5 rounded font-medium" style={{ background: "var(--sentinel-amber)", color: "white" }}>ON GENERATOR</span>
          )}
        </div>
      </div>

      {/* Simplified SLD Layout */}
      <div className="flex flex-col items-center space-y-2">
        {/* MV Section */}
        <div className="flex items-center">
          {mvIncomers.map((node) => (
            <NodeBox key={node.id} node={node} compact={compact} />
          ))}
        </div>

        <VerticalLine energized={sldData.status.mains_healthy} />

        {/* Transformers */}
        <div className="flex items-center gap-4">
          {transformers.map((node) => (
            <NodeBox key={node.id} node={node} compact={compact} />
          ))}
        </div>

        <VerticalLine energized={isMainsEnergized} />

        {/* ATS Level */}
        <div className="flex items-center">
          {/* Mains side */}
          <div className="flex flex-col items-center">
            <span className="text-xs mb-1" style={{ color: "var(--sentinel-text-secondary)" }}>MAINS</span>
            <div className={`w-3 h-3 rounded-full ${isMainsEnergized ? 'bg-green-500' : 'bg-gray-300'}`} />
          </div>

          <ConnectionLine energized={isMainsEnergized} />

          {/* ATS */}
          {atsUnits.map((node) => (
            <NodeBox key={node.id} node={node} compact={compact} />
          ))}

          <ConnectionLine energized={isGenEnergized} />

          {/* Generator side */}
          <div className="flex flex-col items-center">
            <span className="text-xs mb-1" style={{ color: "var(--sentinel-text-secondary)" }}>GEN</span>
            <div className={`w-3 h-3 rounded-full ${isGenEnergized ? 'bg-amber-500' : 'bg-gray-300'}`} />
          </div>
        </div>

        {/* Generator Bank */}
        {generators.length > 0 && (
          <>
            <div className="flex items-center">
              <div className="w-1 h-6 bg-transparent" />
              <div className="w-16" />
              <div className="w-16" />
              <VerticalLine energized={isGenEnergized} />
            </div>
            <div className="flex items-center gap-2 ml-32">
              {generators.slice(0, 4).map((node) => (
                <NodeBox key={node.id} node={node} compact={compact} />
              ))}
            </div>
          </>
        )}

        {/* Output to Switchboard */}
        <VerticalLine energized={true} />

        {/* LV Switchboard */}
        <div className="flex items-center gap-4">
          {switchboards.map((node) => (
            <NodeBox key={node.id} node={node} compact={compact} />
          ))}
        </div>

        {/* UPS Section */}
        {upsUnits.length > 0 && (
          <>
            <VerticalLine energized={true} />
            <div className="flex items-center gap-2">
              {upsUnits.map((node) => (
                <NodeBox key={node.id} node={node} compact={compact} />
              ))}
            </div>
          </>
        )}
      </div>

      {/* Legend */}
      <div className="flex justify-center gap-4 mt-4 pt-4 border-t border-gray-200">
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 bg-green-500 rounded" />
          <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>Energized</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 bg-gray-300 rounded" />
          <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>De-energized</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 bg-amber-500 rounded" />
          <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>Generator</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 bg-red-500 rounded" />
          <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>Fault</span>
        </div>
      </div>
    </div>
  );
}

export default SingleLineDiagram;
