import React, { useState, useEffect } from 'react';
import { Card } from './Card';
import { Badge } from './Badge';
import { Thermometer } from 'lucide-react';
import { api } from '@/lib/api';
import { PageLoading } from './PageLoading';

interface BoundaryStatusPanelProps {
  deviceId?: string;
}

export const BoundaryStatusPanel: React.FC<BoundaryStatusPanelProps> = ({
  deviceId,
}) => {
  const [boundaryStatuses, setBoundaryStatuses] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const fetchBoundaryStatus = async () => {
    setIsLoading(true);
    try {
      const response = await api.getBoundaryStatus(deviceId);
      const statuses = Object.entries(response.data).map(([deviceId, status]) => ({
        deviceId,
        ...(status && typeof status === 'object' ? status : {}),
      }));
      setBoundaryStatuses(statuses);
    } catch (error) {
      console.error('Failed to fetch boundary status:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchBoundaryStatus();
    const interval = setInterval(fetchBoundaryStatus, 5000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deviceId]);

  const getSeverityBadge = (escalationLevel: number) => {
    const variants = {
      0: { color: 'bg-green-500', text: 'Safe' },
      1: { color: 'bg-yellow-500', text: 'Warning' },
      2: { color: 'bg-orange-500', text: 'Alert' },
      3: { color: 'bg-red-500', text: 'Critical' },
      4: { color: 'bg-purple-500', text: 'Emergency' },
    };
    const variant = variants[escalationLevel as keyof typeof variants] || variants[0];
    return (
      <Badge className={`${variant.color} text-white`}>{variant.text}</Badge>
    );
  };

  return (
    <Card className="p-6 rounded-lg">
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          Safety Boundary Status
        </h3>
        <p className="text-sm text-gray-500">
          Real-time monitoring of approach to safety boundaries
        </p>
      </div>

      {isLoading ? (
        <PageLoading compact message="Loading boundary status..." />
      ) : (
        <div className="space-y-3">
          {boundaryStatuses.length === 0 ? (
            <p className="text-gray-500 text-center py-8">
              No boundary monitoring data available
            </p>
          ) : (
            boundaryStatuses.map((status) => (
              <div
                key={status.deviceId}
                className="border-b pb-3 last:border-0"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center space-x-2">
                    <Thermometer className="h-4 w-4 text-gray-400" />
                    <span className="font-medium text-gray-900 dark:text-gray-100">
                      {status.device_name}
                    </span>
                  </div>
                  {getSeverityBadge(status.overall_escalation)}
                </div>

                <div className="grid grid-cols-3 gap-2 text-sm">
                  <div className="text-gray-600">
                    <span className="font-medium">Max Approach:</span>{' '}
                    <span
                      className={`${
                        status.max_approach_percentage >= 95
                          ? 'text-red-600'
                          : status.max_approach_percentage >= 75
                          ? 'text-yellow-600'
                          : 'text-green-600'
                      }`}
                    >
                      {status.max_approach_percentage.toFixed(1)}%
                    </span>
                  </div>
                  <div className="text-gray-600">
                    <span className="font-medium">Warnings:</span>{' '}
                    <span
                      className={`${
                        status.warning_count > 0 ? 'text-yellow-600' : 'text-green-600'
                      }`}
                    >
                      {status.warning_count}
                    </span>
                  </div>
                  <div className="text-gray-600">
                    <span className="font-medium">Critical:</span>{' '}
                    <span
                      className={`${
                        status.critical_count > 0 ? 'text-red-600' : 'text-green-600'
                      }`}
                    >
                      {status.critical_count}
                    </span>
                  </div>
                </div>

                {status.overall_status !== 'safe' && (
                  <div className="mt-2 text-xs text-gray-500">
                    <span className="font-medium">Status:</span>{' '}
                    <span
                      className={`${
                        status.overall_status === 'safe'
                          ? 'text-green-600'
                          : status.overall_status === 'warning'
                          ? 'text-yellow-600'
                          : 'text-red-600'
                      }`}
                    >
                      {status.overall_status.toUpperCase()}
                    </span>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </Card>
  );
};
