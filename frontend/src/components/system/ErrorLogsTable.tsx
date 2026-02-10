/**
 * Error Logs Table
 * 
 * Displays and filters system error logs.
 */

import React, { useState, useEffect } from 'react';
import { AlertTriangle, Filter, RefreshCw } from 'lucide-react';
import { systemApi, type ErrorLog } from '@/lib/api/system';

export function ErrorLogsTable() {
  const [logs, setLogs] = useState<ErrorLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [categoryFilter, setCategoryFilter] = useState<string | undefined>();
  const [severityFilter, setSeverityFilter] = useState<string | undefined>();
  const [resolvedFilter, setResolvedFilter] = useState<boolean | undefined>();
  const [page, setPage] = useState(0);

  const logsPerPage = 20;

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        setLoading(true);
        const result = await systemApi.getErrorLogs({
          category: categoryFilter,
          severity: severityFilter,
          resolved: resolvedFilter,
          limit: logsPerPage,
          offset: page * logsPerPage,
        });
        setLogs(result.logs);
        setError(null);
      } catch (err) {
        setError('Failed to load error logs');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchLogs();
  }, [categoryFilter, severityFilter, resolvedFilter, page]);

  const severityColors: Record<string, string> = {
    warning: 'rgba(245, 158, 11, 0.15)',
    error: 'rgba(220, 38, 38, 0.15)',
    critical: 'rgba(220, 38, 38, 0.25)',
  };

  const severityTextColors: Record<string, string> = {
    warning: 'var(--color-sentinel-amber)',
    error: 'var(--color-sentinel-red)',
    critical: 'var(--color-sentinel-red)',
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
      <div className="flex items-center justify-between mb-6">
        <h3
          className="text-sm font-medium"
          style={{ color: 'var(--color-sentinel-text-primary)' }}
        >
          Error Logs
        </h3>

        <button
          onClick={() => setPage(0)}
          className="p-2 rounded transition-colors hover:opacity-80"
          style={{
            background: 'var(--color-sentinel-bg-secondary)',
            color: 'var(--color-sentinel-text-secondary)',
          }}
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
        <select
          value={categoryFilter || ''}
          onChange={(e) => setCategoryFilter(e.target.value || undefined)}
          className="px-3 py-2 rounded text-xs"
          style={{
            background: 'var(--color-sentinel-bg-secondary)',
            border: '1px solid var(--color-sentinel-border)',
            color: 'var(--color-sentinel-text-primary)',
          }}
        >
          <option value="">All Categories</option>
          <option value="bms">BMS</option>
          <option value="api">API</option>
          <option value="database">Database</option>
          <option value="service">Service</option>
          <option value="other">Other</option>
        </select>

        <select
          value={severityFilter || ''}
          onChange={(e) => setSeverityFilter(e.target.value || undefined)}
          className="px-3 py-2 rounded text-xs"
          style={{
            background: 'var(--color-sentinel-bg-secondary)',
            border: '1px solid var(--color-sentinel-border)',
            color: 'var(--color-sentinel-text-primary)',
          }}
        >
          <option value="">All Severities</option>
          <option value="warning">Warning</option>
          <option value="error">Error</option>
          <option value="critical">Critical</option>
        </select>

        <select
          value={resolvedFilter === undefined ? '' : String(resolvedFilter)}
          onChange={(e) => {
            if (e.target.value === '') setResolvedFilter(undefined);
            else setResolvedFilter(e.target.value === 'true');
          }}
          className="px-3 py-2 rounded text-xs"
          style={{
            background: 'var(--color-sentinel-bg-secondary)',
            border: '1px solid var(--color-sentinel-border)',
            color: 'var(--color-sentinel-text-primary)',
          }}
        >
          <option value="">All Status</option>
          <option value="false">Unresolved</option>
          <option value="true">Resolved</option>
        </select>
      </div>

      {/* Error List */}
      {loading ? (
        <div className="text-center py-8">
          <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2" style={{ color: 'var(--color-sentinel-text-secondary)' }} />
          <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            Loading error logs...
          </span>
        </div>
      ) : logs.length === 0 ? (
        <div className="text-center py-8">
          <AlertTriangle className="w-6 h-6 mx-auto mb-2" style={{ color: 'var(--color-sentinel-green)' }} />
          <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            No error logs found
          </span>
        </div>
      ) : (
        <>
          <div className="space-y-2">
            {logs.map((log) => (
              <div
                key={log.id}
                className="p-3 rounded text-xs"
                style={{
                  background: severityColors[log.severity] || 'var(--color-sentinel-bg-secondary)',
                  border: '1px solid var(--color-sentinel-border)',
                }}
              >
                <div className="flex items-start justify-between gap-3 mb-1">
                  <div className="flex items-start gap-2">
                    <AlertTriangle
                      className="w-4 h-4 mt-0.5 shrink-0"
                      style={{ color: severityTextColors[log.severity] }}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                        {log.component}
                      </div>
                      <div
                        className="mt-0.5"
                        style={{ color: 'var(--color-sentinel-text-secondary)' }}
                      >
                        {log.message}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <span
                      className="px-2 py-0.5 rounded text-xs font-medium"
                      style={{
                        background: severityTextColors[log.severity] + '30',
                        color: severityTextColors[log.severity],
                      }}
                    >
                      {log.severity}
                    </span>
                    {log.resolved && (
                      <span
                        className="px-2 py-0.5 rounded text-xs font-medium"
                        style={{
                          background: 'var(--color-sentinel-green)30',
                          color: 'var(--color-sentinel-green)',
                        }}
                      >
                        Resolved
                      </span>
                    )}
                  </div>
                </div>

                <div
                  className="text-xs"
                  style={{ color: 'var(--color-sentinel-text-disabled)' }}
                >
                  {log.category} • {new Date(log.timestamp).toLocaleString()}
                </div>
              </div>
            ))}
          </div>

          {/* Pagination */}
          <div className="mt-4 flex items-center justify-between text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            <span>
              Showing page {page + 1}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(Math.max(0, page - 1))}
                disabled={page === 0}
                className="px-3 py-1 rounded transition-colors hover:opacity-80 disabled:opacity-50"
                style={{
                  background: 'var(--color-sentinel-bg-secondary)',
                  border: '1px solid var(--color-sentinel-border)',
                  color: 'var(--color-sentinel-text-secondary)',
                }}
              >
                Previous
              </button>
              <button
                onClick={() => setPage(page + 1)}
                disabled={logs.length < logsPerPage}
                className="px-3 py-1 rounded transition-colors hover:opacity-80 disabled:opacity-50"
                style={{
                  background: 'var(--color-sentinel-bg-secondary)',
                  border: '1px solid var(--color-sentinel-border)',
                  color: 'var(--color-sentinel-text-secondary)',
                }}
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
