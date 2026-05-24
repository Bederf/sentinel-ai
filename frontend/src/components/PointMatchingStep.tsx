import { useState, useEffect } from 'react';

import { CheckCircle, AlertTriangle } from 'lucide-react';
import { authorizedFetch } from '../lib/api/client';

const API_BASE_URL = import.meta.env.VITE_API_URL || "";

interface PointMatch {
  bms_point_id: string;
  bms_point_name: string;
  asset_id?: string;
  asset_tag?: string;
  confidence: 'high' | 'medium' | 'low';
  alternatives?: Array<{
    asset_id: string;
    asset_tag: string;
    confidence: number;
  }>;
}

interface PointMatchingStepProps {
  siteId: string;
  columnMappings: Array<{ source_column: string; target_field: string }>;
  onNext: (data: { pointMatches: PointMatch[]; syncSettings: SyncSettings }) => void;
  onBack: () => void;
}

interface SyncSettings {
  poll_frequency_minutes: number;
  store_raw_days: number;
  store_aggregated_years: number;
}

export function PointMatchingStep({ siteId, columnMappings: _columnMappings, onNext, onBack }: PointMatchingStepProps) {
  const [matches, setMatches] = useState<PointMatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncSettings, setSyncSettings] = useState<SyncSettings>({
    poll_frequency_minutes: 5,
    store_raw_days: 90,
    store_aggregated_years: 2
  });
  const [activating, setActivating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadMatches();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadMatches = async () => {
    setLoading(true);
    try {
      const response = await authorizedFetch(`${API_BASE_URL}/api/integration/match-points`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          site_id: siteId,
          log_source_id: 'temp-source-id',
          bms_points: []
        })
      });

      if (!response.ok) {
        throw new Error('Failed to load point matches');
      }

      const data: PointMatch[] = await response.json();
      setMatches(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load matches');
    } finally {
      setLoading(false);
    }
  };

  const handleAssetChange = (pointId: string, newAssetId: string) => {
    setMatches(matches.map(m =>
      m.bms_point_id === pointId
        ? { ...m, asset_id: newAssetId }
        : m
    ));
  };

  const handleActivate = async () => {
    setActivating(true);
    setError(null);

    try {
      const response = await authorizedFetch(`${API_BASE_URL}/api/integration/ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          site_id: siteId,
          log_source_id: 'temp-source-id',
          dry_run: false,
          sync_settings: syncSettings
        })
      });

      if (!response.ok) {
        throw new Error('Failed to activate integration');
      }

      onNext({ pointMatches: matches, syncSettings });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Activation failed');
    } finally {
      setActivating(false);
    }
  };

  const matchedCount = matches.filter(m => m.asset_id).length;
  const highConfidenceCount = matches.filter(m => m.confidence === 'high').length;

  if (loading) {
    return (
      <div className="space-y-4">
        <h3 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Match Points to Assets</h3>
        <p style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading point matches...</p>
      </div>
    );
  }

  const thBase: React.CSSProperties = {
    textAlign: "left",
    fontSize: 12,
    fontWeight: 500,
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    padding: "8px 12px",
    color: "var(--color-sentinel-text-secondary)",
    background: "var(--color-sentinel-bg-secondary)",
    borderBottom: "1px solid var(--color-sentinel-border)",
  };

  const tdBase: React.CSSProperties = {
    padding: "8px 12px",
    fontSize: 14,
    color: "var(--color-sentinel-text-primary)",
    borderBottom: "1px solid var(--color-sentinel-border)",
  };

  const panelCard: React.CSSProperties = {
    background: "var(--color-sentinel-bg-panel)",
    border: "1px solid var(--color-sentinel-border)",
    borderRadius: 8,
    overflow: "hidden",
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Match Points to Assets</h3>
        <p className="mt-2 text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Review auto-detected point-to-asset matches. Adjust if needed, then configure sync settings.
        </p>
      </div>

      <div style={panelCard}>
        <div className="p-4">
          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <div className="text-2xl font-bold" style={{ color: "var(--color-sentinel-blue)" }}>{matches.length}</div>
              <div className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Total Points</div>
            </div>
            <div>
              <div className="text-2xl font-bold" style={{ color: "var(--color-sentinel-green)" }}>{matchedCount}</div>
              <div className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Matched ({matches.length > 0 ? ((matchedCount / matches.length) * 100).toFixed(0) : 0}%)</div>
            </div>
            <div>
              <div className="text-2xl font-bold" style={{ color: "#a78bfa" }}>{highConfidenceCount}</div>
              <div className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>High Confidence</div>
            </div>
          </div>
        </div>
      </div>

      <div style={panelCard}>
        <table className="w-full">
          <thead>
            <tr>
              <th style={thBase}>BMS Point</th>
              <th style={thBase}>Matched Asset</th>
              <th style={thBase}>Confidence</th>
              <th style={thBase}>Status</th>
            </tr>
          </thead>
          <tbody>
            {matches.slice(0, 20).map((match) => (
              <tr key={match.bms_point_id}>
                <td style={tdBase}>
                  <div>
                    <div className="font-mono text-sm">{match.bms_point_id}</div>
                    <div className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>{match.bms_point_name}</div>
                  </div>
                </td>
                <td style={tdBase}>
                  <select
                    value={match.asset_id || ''}
                    onChange={(event) => handleAssetChange(match.bms_point_id, event.target.value)}
                    className="w-48 rounded-md appearance-none cursor-pointer px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-0"
                    style={{
                      background: "var(--color-sentinel-bg-secondary)",
                      border: "1px solid var(--color-sentinel-border)",
                      color: "var(--color-sentinel-text-primary)",
                      boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
                      outline: "none",
                    }}
                    aria-label="Select matched asset"
                  >
                    <option value="">-- Unmatched --</option>
                    {match.alternatives?.map(alt => (
                      <option key={alt.asset_id} value={alt.asset_id}>
                        {alt.asset_tag} ({((alt.confidence ?? 0) * 100).toFixed(0)}%)
                      </option>
                    ))}
                  </select>
                </td>
                <td style={tdBase}>
                  <span
                    className="inline-flex items-center px-2 py-1 text-xs font-medium rounded-full"
                    style={{
                      background: match.confidence === 'high'
                        ? "rgba(16,185,129,0.15)"
                        : match.confidence === 'medium'
                          ? "rgba(245,158,11,0.15)"
                          : "rgba(142,142,142,0.15)",
                      color: match.confidence === 'high'
                        ? "var(--color-sentinel-green)"
                        : match.confidence === 'medium'
                          ? "var(--color-sentinel-amber)"
                          : "var(--color-sentinel-text-secondary)",
                    }}
                  >
                    {match.confidence}
                  </span>
                </td>
                <td style={tdBase}>
                  {match.asset_id ? (
                    <CheckCircle className="w-5 h-5" style={{ color: "var(--color-sentinel-green)" }} />
                  ) : (
                    <AlertTriangle className="w-5 h-5" style={{ color: "var(--color-sentinel-amber)" }} />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {matches.length > 20 && (
          <div className="text-center text-sm py-2" style={{ color: "var(--color-sentinel-text-disabled)" }}>
            Showing 20 of {matches.length} points
          </div>
        )}
      </div>

      <div style={panelCard}>
        <div className="p-4">
          <h3 className="text-lg font-semibold mb-4" style={{ color: "var(--color-sentinel-text-primary)" }}>Sync Configuration</h3>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Poll Frequency
              </label>
              <select
                value={syncSettings.poll_frequency_minutes.toString()}
                onChange={(event) => setSyncSettings({ ...syncSettings, poll_frequency_minutes: parseInt(event.target.value, 10) })}
                className="w-full rounded-md appearance-none cursor-pointer px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-0"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  border: "1px solid var(--color-sentinel-border)",
                  color: "var(--color-sentinel-text-primary)",
                  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
                  outline: "none",
                }}
                aria-label="Poll frequency"
              >
                <option value="1">1 minute</option>
                <option value="5">5 minutes</option>
                <option value="15">15 minutes</option>
                <option value="60">1 hour</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Store Raw Data
              </label>
              <select
                value={syncSettings.store_raw_days.toString()}
                onChange={(event) => setSyncSettings({ ...syncSettings, store_raw_days: parseInt(event.target.value, 10) })}
                className="w-full rounded-md appearance-none cursor-pointer px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-0"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  border: "1px solid var(--color-sentinel-border)",
                  color: "var(--color-sentinel-text-primary)",
                  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
                  outline: "none",
                }}
                aria-label="Store raw data duration"
              >
                <option value="30">30 days</option>
                <option value="90">90 days</option>
                <option value="180">180 days</option>
                <option value="365">1 year</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Store Aggregated Data
              </label>
              <select
                value={syncSettings.store_aggregated_years.toString()}
                onChange={(event) => setSyncSettings({ ...syncSettings, store_aggregated_years: parseInt(event.target.value, 10) })}
                className="w-full rounded-md appearance-none cursor-pointer px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-0"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  border: "1px solid var(--color-sentinel-border)",
                  color: "var(--color-sentinel-text-primary)",
                  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
                  outline: "none",
                }}
                aria-label="Store aggregated data duration"
              >
                <option value="1">1 year</option>
                <option value="2">2 years</option>
                <option value="5">5 years</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div
          className="p-3 rounded-md text-sm flex items-center gap-2"
          style={{
            background: "rgba(220,38,38,0.15)",
            border: "1px solid rgba(220,38,38,0.3)",
            color: "var(--color-sentinel-red)",
          }}
        >
          <span className="font-medium">Error</span>
          <span>{error}</span>
        </div>
      )}

      <div className="flex justify-between">
        <button
          onClick={onBack}
          className="px-4 py-2 text-sm font-medium rounded-md transition-colors"
          style={{
            background: "var(--color-sentinel-bg-secondary)",
            border: "1px solid var(--color-sentinel-border)",
            color: "var(--color-sentinel-text-primary)",
          }}
        >
          Back
        </button>

        <button
          onClick={handleActivate}
          disabled={activating}
          className="px-4 py-2 text-sm font-medium rounded-md transition-colors disabled:opacity-50"
          style={{
            background: "var(--color-sentinel-green)",
            border: "1px solid var(--color-sentinel-green)",
            color: "#fff",
          }}
        >
          {activating ? 'Activating...' : 'Save & Start Sync'}
        </button>
      </div>
    </div>
  );
}
