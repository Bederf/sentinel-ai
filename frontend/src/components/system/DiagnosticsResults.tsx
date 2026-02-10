/**
 * Diagnostics Results Display
 * 
 * Shows SIMBIOT diagnostic results with polling status.
 */

import React, { useState, useEffect } from 'react';
import { CheckCircle, AlertTriangle, RefreshCw } from 'lucide-react';
import { useDiagnostics } from '@/lib/api';

export function DiagnosticsResults() {
  const { result, loading, diagnosticId, runDiagnostics } = useDiagnostics();
  const [pollError, setPollError] = useState<string | null>(null);

  const statusColors: Record<string, any> = {
    pending: { bg: 'rgba(59, 130, 246, 0.15)', color: 'var(--color-sentinel-blue)', label: 'Pending' },
    running: { bg: 'rgba(59, 130, 246, 0.15)', color: 'var(--color-sentinel-blue)', label: 'Running' },
    completed: { bg: 'rgba(16, 185, 129, 0.15)', color: 'var(--color-sentinel-green)', label: 'Completed' },
    failed: { bg: 'rgba(220, 38, 38, 0.15)', color: 'var(--color-sentinel-red)', label: 'Failed' },
  };

  if (!result && !loading && !diagnosticId) {
    return (
      <div
        className="rounded-lg p-6"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
        }}
      >
        <div
          className="text-center py-8"
          style={{ color: 'var(--color-sentinel-text-secondary)' }}
        >
          <AlertTriangle className="w-8 h-8 mx-auto mb-2" />
          <p className="text-sm">
            No diagnostics have been run yet. Start one above to see results.
          </p>
        </div>
      </div>
    );
  }

  const status = result?.status || 'pending';
  const statusConfig = statusColors[status] || statusColors.pending;

  return (
    <div
      className="rounded-lg p-6"
      style={{
        background: 'var(--color-sentinel-bg-panel)',
        border: '1px solid var(--color-sentinel-border)',
      }}
    >
      {/* Header with Status */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div
            className="p-2 rounded"
            style={{ background: statusConfig.bg }}
          >
            {status === 'running' ? (
              <RefreshCw className="w-5 h-5 animate-spin" style={{ color: statusConfig.color }} />
            ) : status === 'completed' ? (
              <CheckCircle className="w-5 h-5" style={{ color: statusConfig.color }} />
            ) : status === 'failed' ? (
              <AlertTriangle className="w-5 h-5" style={{ color: statusConfig.color }} />
            ) : (
              <RefreshCw className="w-5 h-5" style={{ color: statusConfig.color }} />
            )}
          </div>
          <div>
            <h3
              className="text-sm font-medium"
              style={{ color: 'var(--color-sentinel-text-primary)' }}
            >
              Diagnostic Results
            </h3>
            <span
              className="text-xs"
              style={{ color: statusConfig.color }}
            >
              Status: {statusConfig.label}
            </span>
          </div>
        </div>

        {result?.duration_seconds && (
          <span
            className="text-xs"
            style={{ color: 'var(--color-sentinel-text-secondary)' }}
          >
            Completed in {result.duration_seconds}s
          </span>
        )}
      </div>

      {/* Results Content */}
      {loading ? (
        <div className="text-center py-8">
          <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2" style={{ color: 'var(--color-sentinel-blue)' }} />
          <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            Running diagnostics... This may take 30-60 seconds.
          </p>
        </div>
      ) : result ? (
        <div className="space-y-4">
          {/* Issues Found */}
          {result.issues_found && result.issues_found.length > 0 && (
            <div>
              <h4
                className="text-xs font-medium mb-2"
                style={{ color: 'var(--color-sentinel-text-primary)' }}
              >
                Issues Found
              </h4>
              <ul className="space-y-1">
                {result.issues_found.map((issue, i) => (
                  <li
                    key={i}
                    className="text-xs p-2 rounded flex gap-2"
                    style={{
                      background: 'rgba(220, 38, 38, 0.1)',
                      color: 'var(--color-sentinel-text-secondary)',
                    }}
                  >
                    <span style={{ color: 'var(--color-sentinel-red)' }}>!</span>
                    <span>{issue}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Recommendations */}
          {result.recommendations && result.recommendations.length > 0 && (
            <div>
              <h4
                className="text-xs font-medium mb-2"
                style={{ color: 'var(--color-sentinel-text-primary)' }}
              >
                Recommendations
              </h4>
              <ul className="space-y-1">
                {result.recommendations.map((rec, i) => (
                  <li
                    key={i}
                    className="text-xs p-2 rounded flex gap-2"
                    style={{
                      background: 'rgba(16, 185, 129, 0.1)',
                      color: 'var(--color-sentinel-text-secondary)',
                    }}
                  >
                    <span style={{ color: 'var(--color-sentinel-green)' }}>✓</span>
                    <span>{rec}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Error Message */}
          {result.error_message && (
            <div
              className="p-3 rounded text-xs"
              style={{
                background: 'rgba(220, 38, 38, 0.1)',
                border: '1px solid rgba(220, 38, 38, 0.3)',
                color: 'var(--color-sentinel-text-secondary)',
              }}
            >
              {result.error_message}
            </div>
          )}

          {/* Next Steps */}
          {result.next_steps && result.next_steps.length > 0 && (
            <div>
              <h4
                className="text-xs font-medium mb-2"
                style={{ color: 'var(--color-sentinel-text-primary)' }}
              >
                Next Steps
              </h4>
              <ol className="space-y-1 pl-4">
                {result.next_steps.map((step, i) => (
                  <li
                    key={i}
                    className="text-xs list-decimal"
                    style={{ color: 'var(--color-sentinel-text-secondary)' }}
                  >
                    {step}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
