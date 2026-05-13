/**
 * ATS Status Panel - Bolt-on Module
 *
 * Automatic Transfer Switch monitoring:
 * - Source position (Mains/Generator)
 * - Breaker states
 * - Transfer history
 * - Interlock status
 */

import { useState, useEffect, useCallback } from 'react';
import { energyCentreApi } from '../../lib/energyCentreApi';
import type { ATSStatus } from '../../lib/energyCentreApi';

interface ATSStatusPanelProps {
  siteId: string;
  compact?: boolean;
  onTransferEvent?: (ats: ATSStatus, previousPosition: string) => void;
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

const positionColors: Record<string, string> = {
  mains: 'blue',
  generator: 'amber',
  off: 'gray',
  transitioning: 'purple',
  parallel: 'cyan',
};

const breakerColors: Record<string, string> = {
  closed: 'green',
  open: 'gray',
  tripped: 'red',
};

export function ATSStatusPanel({ siteId, compact = false, onTransferEvent }: ATSStatusPanelProps) {
  const [atsUnits, setAtsUnits] = useState<ATSStatus[]>([]);
  const [previousPositions, setPreviousPositions] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      const units = await energyCentreApi.getATSUnits(siteId);

      // Get detailed status for each ATS
      const statuses = await Promise.all(
        units.map(ats => energyCentreApi.getATSStatus(ats.ats_id))
      );

      // Check for transfer events
      if (onTransferEvent) {
        statuses.forEach(status => {
          const prevPos = previousPositions[status.ats_id];
          if (prevPos && prevPos !== status.position) {
            onTransferEvent(status, prevPos);
          }
        });
      }

      // Update previous positions
      const newPositions: Record<string, string> = {};
      statuses.forEach(s => {
        newPositions[s.ats_id] = s.position;
      });
      setPreviousPositions(newPositions);

      setAtsUnits(statuses);
      setLoading(false);
    } catch (_err) {
      setLoading(false);
    }
  }, [siteId, onTransferEvent, previousPositions]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 2000);
    return () => clearInterval(interval);
  }, [loadData]);

  if (loading) {
    return (
      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Transfer Switch</h3>
        <div className="animate-pulse h-24 bg-gray-100 rounded mt-4" />
      </div>
    );
  }

  if (atsUnits.length === 0) {
    return (
      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Transfer Switch</h3>
        <p style={{ color: "var(--sentinel-text-secondary)" }}>No ATS data available</p>
      </div>
    );
  }

  const ats = atsUnits[0]; // Primary ATS

  if (compact) {
    const accentColor = sentinelColors[positionColors[ats.position]] || sentinelColors.gray;
    return (
      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)", borderTop: `3px solid ${accentColor}` }}>
        <div className="flex items-center justify-between">
          <div>
            <span style={{ color: "var(--sentinel-text-secondary)" }}>ATS Position</span>
            <span className="text-2xl font-bold tabular-nums capitalize" style={{ color: "var(--sentinel-text-primary)" }}>{ats.position}</span>
          </div>
          <div className="flex flex-col items-center gap-1">
            <div className={`w-4 h-4 rounded-full ${ats.sources.mains.available ? 'bg-green-500' : 'bg-gray-300'}`} />
            <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>Mains</span>
          </div>
          <div className="flex flex-col items-center gap-1">
            <div className={`w-4 h-4 rounded-full ${ats.sources.generator.available ? 'bg-amber-500' : 'bg-gray-300'}`} />
            <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>Gen</span>
          </div>
        </div>
      </div>
    );
  }

  const positionColor = sentinelColors[positionColors[ats.position]] || sentinelColors.gray;

  return (
    <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>{ats.name}</h3>
          <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>{ats.type} - {ats.transfer_mode} transition</span>
        </div>
        <span className="text-xs px-2 py-0.5 rounded font-medium" style={{ background: positionColor, color: "white" }}>
          {ats.position.toUpperCase()}
        </span>
      </div>

      {/* Visual ATS Representation */}
      <div className="mt-4 p-4 bg-gray-50 rounded-lg">
        <div className="flex items-center justify-center gap-4">
          {/* Mains Source */}
          <div className="flex flex-col items-center">
            <div className={`
              w-12 h-12 rounded-lg flex items-center justify-center
              ${ats.sources.mains.available ? 'bg-blue-100 border-2 border-blue-500' : 'bg-gray-100 border border-gray-300'}
            `}>
              <span className={ats.sources.mains.available ? 'text-blue-700 font-bold' : 'text-gray-400'}>
                MAINS
              </span>
            </div>
            <span className="text-xs px-1 py-0.5 rounded font-medium mt-1" style={{ background: sentinelColors[breakerColors[ats.sources.mains.breaker]] || sentinelColors.gray, color: "white" }}>
              {ats.sources.mains.breaker.toUpperCase()}
            </span>
          </div>

          {/* Connection Lines */}
          <div className="flex flex-col items-center">
            <div className={`w-8 h-1 ${ats.position === 'mains' ? 'bg-blue-500' : 'bg-gray-300'}`} />
          </div>

          {/* ATS Box */}
          <div className={`
            w-16 h-16 rounded-lg flex items-center justify-center
            ${positionColors[ats.position] === 'blue' ? 'bg-blue-100 border-2 border-blue-500' :
              positionColors[ats.position] === 'amber' ? 'bg-amber-100 border-2 border-amber-500' :
                'bg-gray-100 border-2 border-gray-400'}
          `}>
            <span className="font-bold">ATS</span>
          </div>

          {/* Connection Lines */}
          <div className="flex flex-col items-center">
            <div className={`w-8 h-1 ${ats.position === 'generator' ? 'bg-amber-500' : 'bg-gray-300'}`} />
          </div>

          {/* Generator Source */}
          <div className="flex flex-col items-center">
            <div className={`
              w-12 h-12 rounded-lg flex items-center justify-center
              ${ats.sources.generator.available ? 'bg-amber-100 border-2 border-amber-500' : 'bg-gray-100 border border-gray-300'}
            `}>
              <span className={ats.sources.generator.available ? 'text-amber-700 font-bold' : 'text-gray-400'}>
                GEN
              </span>
            </div>
            <span className="text-xs px-1 py-0.5 rounded font-medium mt-1" style={{ background: sentinelColors[breakerColors[ats.sources.generator.breaker]] || sentinelColors.gray, color: "white" }}>
              {ats.sources.generator.breaker.toUpperCase()}
            </span>
          </div>
        </div>
      </div>

      {/* Status Details */}
      <div className="grid grid-cols-3 gap-4 mt-4">
        <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
          <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>Interlocks</span>
          <div className="flex gap-1 mt-1">
            <span className="text-xs px-1 py-0.5 rounded font-medium" style={{ background: sentinelColors[ats.interlocks.mechanical_ok ? 'green' : 'red'], color: "white" }}>
              Mech {ats.interlocks.mechanical_ok ? 'OK' : 'FAIL'}
            </span>
            <span className="text-xs px-1 py-0.5 rounded font-medium" style={{ background: sentinelColors[ats.interlocks.electrical_ok ? 'green' : 'red'], color: "white" }}>
              Elec {ats.interlocks.electrical_ok ? 'OK' : 'FAIL'}
            </span>
          </div>
        </div>
        <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
          <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>Transfer Time</span>
          <span className="font-bold" style={{ color: "var(--sentinel-text-primary)" }}>{ats.transfer_stats.last_transfer_time_ms} ms</span>
        </div>
        <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
          <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>Total Transfers</span>
          <span className="font-bold" style={{ color: "var(--sentinel-text-primary)" }}>{ats.transfer_stats.total_transfers}</span>
        </div>
      </div>

      {/* Last Transfer */}
      {ats.transfer_stats.last_transfer && (
        <div className="mt-4 pt-4 border-t border-gray-200">
          <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>Last Transfer</span>
          <span style={{ color: "var(--sentinel-text-secondary)" }}>
            {new Date(ats.transfer_stats.last_transfer).toLocaleString()} - {ats.transfer_stats.last_reason || 'Unknown'}
          </span>
        </div>
      )}
    </div>
  );
}

export default ATSStatusPanel;
