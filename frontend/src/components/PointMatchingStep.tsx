// PointMatchingStep.tsx
import { useState, useEffect } from 'react';
import { Badge, Button, Card, Callout, Select, SelectItem, Table, TableBody, TableCell, TableHead, TableRow, Text, Title } from '@tremor/react';
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

  // Load point matches
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
          bms_points: [] // Backend will extract from uploaded file
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
      // Save sync settings and activate
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
        <Title>Match Points to Assets</Title>
        <Text>Loading point matches...</Text>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <Title>Match Points to Assets</Title>
        <Text className="mt-2">
          Review auto-detected point-to-asset matches. Adjust if needed, then configure sync settings.
        </Text>
      </div>

      {/* Match summary */}
      <Card className="p-4">
        <div className="grid grid-cols-3 gap-4 text-center">
          <div>
            <div className="text-2xl font-bold text-blue-500">{matches.length}</div>
            <div className="text-sm text-gray-500">Total Points</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-green-500">{matchedCount}</div>
            <div className="text-sm text-gray-500">Matched ({matches.length > 0 ? ((matchedCount / matches.length) * 100).toFixed(0) : 0}%)</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-purple-500">{highConfidenceCount}</div>
            <div className="text-sm text-gray-500">High Confidence</div>
          </div>
        </div>
      </Card>

      {/* Point matching table (show first 20) */}
      <Card>
        <Table>
          <TableHead>
            <TableRow>
              <TableHead>BMS Point</TableHead>
              <TableHead>Matched Asset</TableHead>
              <TableHead>Confidence</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHead>
          <TableBody>
            {matches.slice(0, 20).map((match) => (
              <TableRow key={match.bms_point_id}>
                <TableCell>
                  <div>
                    <div className="font-mono text-sm">{match.bms_point_id}</div>
                    <div className="text-xs text-gray-500">{match.bms_point_name}</div>
                  </div>
                </TableCell>
                <TableCell>
                  <Select
                    value={match.asset_id || ''}
                    onChange={(value: any) => handleAssetChange(match.bms_point_id, value as string)}
                    placeholder="Select asset..."
                    className="w-48"
                  >
                    <SelectItem value="">-- Unmatched --</SelectItem>
                    {match.alternatives?.map(alt => (
                      <SelectItem key={alt.asset_id} value={alt.asset_id}>
                        {alt.asset_tag} ({((alt.confidence ?? 0) * 100).toFixed(0)}%)
                      </SelectItem>
                    ))}
                  </Select>
                </TableCell>
                <TableCell>
                  <Badge
                    color={match.confidence === 'high' ? 'green' : match.confidence === 'medium' ? 'yellow' : 'gray'}
                  >
                    {match.confidence}
                  </Badge>
                </TableCell>
                <TableCell>
                  {match.asset_id ? (
                    <CheckCircle className="w-5 h-5 text-green-500" />
                  ) : (
                    <AlertTriangle className="w-5 h-5 text-yellow-500" />
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {matches.length > 20 && (
          <div className="text-center text-sm text-gray-500 mt-2">
            Showing 20 of {matches.length} points
          </div>
        )}
      </Card>

      {/* Sync settings */}
      <Card className="p-4">
        <Title className="text-lg">Sync Configuration</Title>
        <div className="grid grid-cols-3 gap-4 mt-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Poll Frequency
            </label>
            <Select
              value={syncSettings.poll_frequency_minutes.toString()}
              onChange={(value: any) => setSyncSettings({ ...syncSettings, poll_frequency_minutes: parseInt(value as string) })}
            >
              <SelectItem value="1">1 minute</SelectItem>
              <SelectItem value="5">5 minutes</SelectItem>
              <SelectItem value="15">15 minutes</SelectItem>
              <SelectItem value="60">1 hour</SelectItem>
            </Select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Store Raw Data
            </label>
            <Select
              value={syncSettings.store_raw_days.toString()}
              onChange={(value: any) => setSyncSettings({ ...syncSettings, store_raw_days: parseInt(value as string) })}
            >
              <SelectItem value="30">30 days</SelectItem>
              <SelectItem value="90">90 days</SelectItem>
              <SelectItem value="180">180 days</SelectItem>
              <SelectItem value="365">1 year</SelectItem>
            </Select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Store Aggregated Data
            </label>
            <Select
              value={syncSettings.store_aggregated_years.toString()}
              onChange={(value: any) => setSyncSettings({ ...syncSettings, store_aggregated_years: parseInt(value as string) })}
            >
              <SelectItem value="1">1 year</SelectItem>
              <SelectItem value="2">2 years</SelectItem>
              <SelectItem value="5">5 years</SelectItem>
            </Select>
          </div>
        </div>
      </Card>

      {/* Error */}
      {error && (
        <Callout title="Error" color="rose">{error}</Callout>
      )}

      {/* Actions */}
      <div className="flex justify-between">
        <Button onClick={onBack} variant="secondary" color="gray">
          Back
        </Button>

        <Button
          onClick={handleActivate}
          disabled={activating}
          color="green"
        >
          {activating ? 'Activating...' : 'Save & Start Sync'}
        </Button>
      </div>
    </div>
  );
}
