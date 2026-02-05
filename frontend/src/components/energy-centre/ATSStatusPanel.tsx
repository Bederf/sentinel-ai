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
import { Card, Title, Text, Badge, Grid, Flex, Metric } from '@tremor/react';
import { energyCentreApi } from '../../lib/energyCentreApi';
import type { ATSStatus } from '../../lib/energyCentreApi';

interface ATSStatusPanelProps {
  siteId: string;
  compact?: boolean;
  onTransferEvent?: (ats: ATSStatus, previousPosition: string) => void;
}

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
      <Card>
        <Title>Transfer Switch</Title>
        <div className="animate-pulse h-24 bg-gray-100 rounded mt-4" />
      </Card>
    );
  }

  if (atsUnits.length === 0) {
    return (
      <Card>
        <Title>Transfer Switch</Title>
        <Text className="text-gray-500">No ATS data available</Text>
      </Card>
    );
  }

  const ats = atsUnits[0]; // Primary ATS

  if (compact) {
    return (
      <Card decoration="top" decorationColor={positionColors[ats.position] || 'gray'}>
        <Flex justifyContent="between" alignItems="center">
          <div>
            <Text>ATS Position</Text>
            <Metric className="capitalize">{ats.position}</Metric>
          </div>
          <div className="flex flex-col items-center gap-1">
            <div className={`w-4 h-4 rounded-full ${ats.sources.mains.available ? 'bg-green-500' : 'bg-gray-300'}`} />
            <Text className="text-xs">Mains</Text>
          </div>
          <div className="flex flex-col items-center gap-1">
            <div className={`w-4 h-4 rounded-full ${ats.sources.generator.available ? 'bg-amber-500' : 'bg-gray-300'}`} />
            <Text className="text-xs">Gen</Text>
          </div>
        </Flex>
      </Card>
    );
  }

  return (
    <Card>
      <Flex justifyContent="between" alignItems="start">
        <div>
          <Title>{ats.name}</Title>
          <Text className="text-xs">{ats.type} - {ats.transfer_mode} transition</Text>
        </div>
        <Badge color={positionColors[ats.position] || 'gray'} size="lg">
          {ats.position.toUpperCase()}
        </Badge>
      </Flex>

      {/* Visual ATS Representation */}
      <div className="mt-4 p-4 bg-gray-50 rounded-lg">
        <div className="flex items-center justify-center gap-4">
          {/* Mains Source */}
          <div className="flex flex-col items-center">
            <div className={`
              w-12 h-12 rounded-lg flex items-center justify-center
              ${ats.sources.mains.available ? 'bg-blue-100 border-2 border-blue-500' : 'bg-gray-100 border border-gray-300'}
            `}>
              <Text className={ats.sources.mains.available ? 'text-blue-700 font-bold' : 'text-gray-400'}>
                MAINS
              </Text>
            </div>
            <Badge color={breakerColors[ats.sources.mains.breaker]} className="mt-1">
              {ats.sources.mains.breaker.toUpperCase()}
            </Badge>
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
            <Text className="font-bold">ATS</Text>
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
              <Text className={ats.sources.generator.available ? 'text-amber-700 font-bold' : 'text-gray-400'}>
                GEN
              </Text>
            </div>
            <Badge color={breakerColors[ats.sources.generator.breaker]} className="mt-1">
              {ats.sources.generator.breaker.toUpperCase()}
            </Badge>
          </div>
        </div>
      </div>

      {/* Status Details */}
      <Grid numItems={3} className="gap-4 mt-4">
        <Card>
          <Text className="text-xs text-gray-500">Interlocks</Text>
          <div className="flex gap-1 mt-1">
            <Badge color={ats.interlocks.mechanical_ok ? 'green' : 'red'} size="xs">
              Mech {ats.interlocks.mechanical_ok ? 'OK' : 'FAIL'}
            </Badge>
            <Badge color={ats.interlocks.electrical_ok ? 'green' : 'red'} size="xs">
              Elec {ats.interlocks.electrical_ok ? 'OK' : 'FAIL'}
            </Badge>
          </div>
        </Card>
        <Card>
          <Text className="text-xs text-gray-500">Transfer Time</Text>
          <Text className="font-bold">{ats.transfer_stats.last_transfer_time_ms} ms</Text>
        </Card>
        <Card>
          <Text className="text-xs text-gray-500">Total Transfers</Text>
          <Text className="font-bold">{ats.transfer_stats.total_transfers}</Text>
        </Card>
      </Grid>

      {/* Last Transfer */}
      {ats.transfer_stats.last_transfer && (
        <div className="mt-4 pt-4 border-t border-gray-200">
          <Text className="text-xs text-gray-500">Last Transfer</Text>
          <Text>
            {new Date(ats.transfer_stats.last_transfer).toLocaleString()} - {ats.transfer_stats.last_reason || 'Unknown'}
          </Text>
        </div>
      )}
    </Card>
  );
}

export default ATSStatusPanel;
