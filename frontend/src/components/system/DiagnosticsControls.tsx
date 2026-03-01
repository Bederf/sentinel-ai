/**
 * Diagnostics Controls
 *
 * Interface for triggering SIMBIOT diagnostics workflow.
 */

import React, { useState } from 'react';
import { Play, AlertCircle } from 'lucide-react';
import { systemApi } from '@/lib/api';

interface DiagnosticsControlsProps {
  onDiagnosticsStart?: (diagnosticId: string) => void;
}

export function DiagnosticsControls({ onDiagnosticsStart }: DiagnosticsControlsProps) {
  const [selectedTarget, setSelectedTarget] = useState('full_system');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRunTime, setLastRunTime] = useState<string | null>(null);

  const targets = [
    { value: 'full_system', label: 'Full System' },
    { value: 'building:primary', label: 'Primary Building' },
    { value: 'component:device_manager', label: 'Device Manager' },
    { value: 'component:api_health', label: 'API Health' },
  ];

  const handleRunDiagnostics = async () => {
    setLoading(true);
    setError(null);

    try {
      const result = await systemApi.runDiagnostics(selectedTarget);
      setLastRunTime(new Date().toLocaleTimeString());
      if (onDiagnosticsStart) {
        onDiagnosticsStart(result.diagnostic_id);
      }
    } catch (err) {
      setError('Failed to start diagnostics. Please try again.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="rounded-lg p-6"
      style={{
        background: 'var(--color-sentinel-bg-panel)',
        border: '1px solid var(--color-sentinel-border)',
      }}
    >
      {/* Header */}
      <h3
        className="text-sm font-medium mb-4"
        style={{ color: 'var(--color-sentinel-text-primary)' }}
      >
        Run Diagnostics
      </h3>

      {/* Target Selection */}
      <div className="mb-4">
        <label
          className="text-xs font-medium mb-2 block"
          style={{ color: 'var(--color-sentinel-text-secondary)' }}
        >
          Diagnostic Target
        </label>
        <select
          value={selectedTarget}
          onChange={(e) => setSelectedTarget(e.target.value)}
          className="w-full px-3 py-2 rounded text-sm"
          style={{
            background: 'var(--color-sentinel-bg-secondary)',
            border: '1px solid var(--color-sentinel-border)',
            color: 'var(--color-sentinel-text-primary)',
          }}
        >
          {targets.map((target) => (
            <option key={target.value} value={target.value}>
              {target.label}
            </option>
          ))}
        </select>
      </div>

      {/* Description */}
      <p
        className="text-xs mb-4"
        style={{ color: 'var(--color-sentinel-text-secondary)' }}
      >
        Diagnostics will run the following SIMBIOT tools:
        <span className="block mt-2 ml-2">
          • Device inventory scan
          <br />
          • DALI gateway discovery
          <br />
          • Building configuration check
          <br />
          • Active alarms search
          <br />
          • Health score calculation
          <br />
          • Asset detail inspection
        </span>
      </p>

      {/* Error message */}
      {error && (
        <div
          className="mb-4 p-3 rounded flex items-start gap-2 text-xs"
          style={{
            background: 'rgba(220, 38, 38, 0.1)',
            border: '1px solid rgba(220, 38, 38, 0.3)',
          }}
        >
          <AlertCircle className="w-4 h-4 mt-0.5" style={{ color: 'var(--color-sentinel-red)' }} />
          <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            {error}
          </span>
        </div>
      )}

      {/* Run Button */}
      <div className="flex items-center justify-between">
        <button
          onClick={handleRunDiagnostics}
          disabled={loading}
          className="px-4 py-2 rounded text-sm font-medium flex items-center gap-2 transition-colors hover:opacity-80 disabled:opacity-50"
          style={{
            background: 'var(--color-sentinel-blue)',
            color: 'white',
          }}
        >
          <Play className="w-4 h-4" />
          {loading ? 'Running...' : 'Run Diagnostics'}
        </button>

        {lastRunTime && (
          <span
            className="text-xs"
            style={{ color: 'var(--color-sentinel-text-secondary)' }}
          >
            Last run: {lastRunTime}
          </span>
        )}
      </div>

      {/* Info */}
      <div
        className="mt-4 pt-4 border-t"
        style={{ borderColor: 'var(--color-sentinel-border)' }}
      >
        <p
          className="text-xs"
          style={{ color: 'var(--color-sentinel-text-disabled)' }}
        >
          Diagnostics typically complete within 30-60 seconds. Results will appear below once completed.
        </p>
      </div>
    </div>
  );
}
