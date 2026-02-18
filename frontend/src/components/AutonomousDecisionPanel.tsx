import React, { useState, useEffect } from 'react';
import { Card } from './Card';
import { Badge } from './Badge';
import { RefreshCw, CheckCircle, XCircle, AlertTriangle, Clock } from 'lucide-react';
import { api } from '@/lib/api';

interface AutonomousDecisionPanelProps {
  autoRefresh?: boolean;
  refreshInterval?: number;
}

export const AutonomousDecisionPanel: React.FC<AutonomousDecisionPanelProps> = ({
  autoRefresh = true,
  refreshInterval = 5000,
}) => {
  const [decisions, setDecisions] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const fetchDecisions = async () => {
    setIsLoading(true);
    try {
      const response = await api.getAutonomousDecisions({ limit: 10 });
      setDecisions(response.data);
    } catch (error) {
      console.error('Failed to fetch autonomous decisions:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (autoRefresh) {
      fetchDecisions();
      const interval = setInterval(fetchDecisions, refreshInterval);
      return () => clearInterval(interval);
    }
  }, [autoRefresh, refreshInterval]);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'success':
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'blocked':
      case 'failed':
        return <XCircle className="h-4 w-4 text-red-500" />;
      case 'executing':
        return <RefreshCw className="h-4 w-4 text-blue-500 animate-spin" />;
      case 'warning':
        return <AlertTriangle className="h-4 w-4 text-yellow-500" />;
      default:
        return <Clock className="h-4 w-4 text-gray-500" />;
    }
  };

  const getEscalationBadge = (level: number) => {
    const variants = {
      0: { color: 'bg-gray-400', text: 'None' },
      1: { color: 'bg-yellow-400', text: 'Warning' },
      2: { color: 'bg-orange-400', text: 'Alert' },
      3: { color: 'bg-red-400', text: 'Critical' },
      4: { color: 'bg-purple-400', text: 'Emergency' },
    };
    const variant = variants[level as keyof typeof variants] || variants[0];
    return <Badge className={`${variant.color} text-white`}>{variant.text}</Badge>;
  };

  return (
    <Card className="p-6 rounded-lg">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          Autonomous Decisions
        </h3>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <RefreshCw className="h-6 w-6 animate-spin text-blue-500" />
          <span className="ml-2 text-gray-500">Loading decisions...</span>
        </div>
      ) : (
        <div className="space-y-3">
          {decisions.length === 0 ? (
            <p className="text-gray-500 text-center py-8">
              No autonomous decisions yet
            </p>
          ) : (
            decisions.map((decision) => (
              <div
                key={decision.id}
                className="border rounded-lg p-3 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center space-x-2">
                    {getStatusIcon(decision.status)}
                    <span className="font-medium text-gray-900 dark:text-gray-100">
                      {decision.device_name}
                    </span>
                  </div>
                  <div className="flex items-center space-x-2">
                    {getEscalationBadge(decision.escalation_level)}
                    <span className="text-xs text-gray-500">
                      {new Date(decision.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                </div>

                <div className="text-sm text-gray-600 dark:text-gray-400">
                  {decision.point_name}: {decision.current_value} → {decision.target_value}
                </div>

                {decision.decision_rationale && (
                  <div className="mt-2 text-xs text-gray-500 italic">
                    {decision.decision_rationale.length > 100
                      ? decision.decision_rationale.substring(0, 100) + '...'
                      : decision.decision_rationale}
                  </div>
                )}

                {decision.execution_time_ms && (
                  <div className="mt-1 text-xs text-gray-400">
                    Executed in {decision.execution_time_ms.toFixed(1)}ms
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}

      <div className="mt-4 pt-4 border-t">
        <button
          onClick={fetchDecisions}
          className="text-sm text-blue-600 hover:text-blue-800 transition-colors"
        >
          Refresh History
        </button>
      </div>
    </Card>
  );
};
