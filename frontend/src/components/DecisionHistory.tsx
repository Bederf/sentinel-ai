import React, { useState, useEffect } from 'react';
import { Card } from './Card';
import { Badge } from './Badge';
import { Download, Filter, ChevronDown, ChevronUp } from 'lucide-react';
import { api } from '@/lib/api';

interface Decision {
  id: string;
  timestamp: string;
  device_id: string;
  device_name: string;
  point_name: string;
  current_value: number;
  target_value: number;
  status: string;
  decision_rationale: string;
  execution_time_ms: number;
  safety_score: number;
  escalation_level: number;
}

interface DecisionHistoryProps {
  maxResults?: number;
}

export const DecisionHistory: React.FC<DecisionHistoryProps> = ({
  maxResults = 50,
}) => {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [filteredDecisions, setFilteredDecisions] = useState<Decision[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [filters, setFilters] = useState({
    deviceFilter: '',
    statusFilter: 'all',
    dateFilter: 'all',
  });
  const [showFilters, setShowFilters] = useState(false);

  const fetchDecisions = async () => {
    setIsLoading(true);
    try {
      const response = await api.getAutonomousDecisions({ limit: maxResults });
      const data = response.data || [];
      setDecisions(Array.isArray(data) ? data : []);
      applyFilters(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('Failed to fetch decision history:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDecisions();
    const interval = setInterval(fetchDecisions, 30000); // Refresh every 30 seconds
    return () => clearInterval(interval);
  }, [maxResults]);

  useEffect(() => {
    applyFilters(decisions);
  }, [filters, decisions]);

  const applyFilters = (data: Decision[]) => {
    let filtered = data;

    if (filters.deviceFilter) {
      filtered = filtered.filter((d) =>
        d.device_name
          .toLowerCase()
          .includes(filters.deviceFilter.toLowerCase())
      );
    }

    if (filters.statusFilter !== 'all') {
      filtered = filtered.filter((d) => d.status === filters.statusFilter);
    }

    if (filters.dateFilter !== 'all') {
      const now = new Date();
      const filterDate = new Date();

      if (filters.dateFilter === 'hour') {
        filterDate.setHours(now.getHours() - 1);
      } else if (filters.dateFilter === 'day') {
        filterDate.setDate(now.getDate() - 1);
      } else if (filters.dateFilter === 'week') {
        filterDate.setDate(now.getDate() - 7);
      }

      filtered = filtered.filter(
        (d) => new Date(d.timestamp) >= filterDate
      );
    }

    setFilteredDecisions(filtered);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'success':
        return 'bg-green-500';
      case 'blocked':
      case 'failed':
        return 'bg-red-500';
      case 'executing':
        return 'bg-blue-500';
      case 'warning':
        return 'bg-yellow-500';
      default:
        return 'bg-gray-500';
    }
  };

  const getEscalationColor = (level: number) => {
    switch (level) {
      case 0:
        return 'bg-green-500';
      case 1:
        return 'bg-yellow-500';
      case 2:
        return 'bg-orange-500';
      case 3:
        return 'bg-red-500';
      case 4:
        return 'bg-purple-500';
      default:
        return 'bg-gray-500';
    }
  };

  const calculateMetrics = () => {
    const successCount = decisions.filter((d) => d.status === 'success').length;
    const failureCount = decisions.filter((d) => d.status === 'failed').length;
    const successRate =
      decisions.length > 0
        ? ((successCount / decisions.length) * 100).toFixed(1)
        : '0';
    const avgSafetyScore =
      decisions.length > 0
        ? (decisions.reduce((sum, d) => sum + (d.safety_score || 0), 0) /
            decisions.length).toFixed(2)
        : '0';
    const avgExecutionTime =
      decisions.length > 0
        ? (decisions.reduce((sum, d) => sum + (d.execution_time_ms || 0), 0) /
            decisions.length).toFixed(1)
        : '0';

    return {
      successRate,
      failureCount,
      avgSafetyScore,
      avgExecutionTime,
    };
  };

  const exportAsCSV = () => {
    const headers = [
      'Timestamp',
      'Device',
      'Point',
      'Current Value',
      'Target Value',
      'Status',
      'Safety Score',
      'Execution Time (ms)',
    ];
    const rows = filteredDecisions.map((d) => [
      new Date(d.timestamp).toISOString(),
      d.device_name,
      d.point_name,
      d.current_value,
      d.target_value,
      d.status,
      d.safety_score,
      d.execution_time_ms,
    ]);

    const csvContent = [
      headers.join(','),
      ...rows.map((row) => row.join(',')),
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `decision-history-${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
  };

  const metrics = calculateMetrics();

  return (
    <div className="space-y-4">
      {/* Metrics Overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4 rounded-lg">
          <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">
            Success Rate
          </div>
          <div className="text-2xl font-bold text-green-600">
            {metrics.successRate}%
          </div>
        </Card>
        <Card className="p-4 rounded-lg">
          <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">
            Failures
          </div>
          <div className="text-2xl font-bold text-red-600">
            {metrics.failureCount}
          </div>
        </Card>
        <Card className="p-4 rounded-lg">
          <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">
            Avg Safety Score
          </div>
          <div className="text-2xl font-bold text-blue-600">
            {metrics.avgSafetyScore}
          </div>
        </Card>
        <Card className="p-4 rounded-lg">
          <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">
            Avg Execution
          </div>
          <div className="text-2xl font-bold text-purple-600">
            {metrics.avgExecutionTime}ms
          </div>
        </Card>
      </div>

      {/* Filter and Export Controls */}
      <Card className="p-4 rounded-lg">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center space-x-2">
            <Filter className="h-4 w-4 text-gray-600" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Decision History
            </h3>
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setShowFilters(!showFilters)}
              className="px-3 py-1 bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded text-sm hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
            >
              Filters
            </button>
            <button
              onClick={exportAsCSV}
              className="px-3 py-1 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 transition-colors flex items-center space-x-1"
            >
              <Download className="h-4 w-4" />
              <span>Export</span>
            </button>
          </div>
        </div>

        {/* Filters */}
        {showFilters && (
          <div className="mb-4 p-4 bg-gray-50 dark:bg-gray-800 rounded space-y-3 border">
            <div>
              <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                Device
              </label>
              <input
                type="text"
                value={filters.deviceFilter}
                onChange={(e) =>
                  setFilters({ ...filters, deviceFilter: e.target.value })
                }
                placeholder="Search by device name..."
                className="w-full px-3 py-2 border rounded text-sm text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                  Status
                </label>
                <select
                  value={filters.statusFilter}
                  onChange={(e) =>
                    setFilters({ ...filters, statusFilter: e.target.value })
                  }
                  className="w-full px-3 py-2 border rounded text-sm text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700"
                >
                  <option value="all">All Statuses</option>
                  <option value="success">Success</option>
                  <option value="failed">Failed</option>
                  <option value="blocked">Blocked</option>
                  <option value="executing">Executing</option>
                  <option value="warning">Warning</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                  Date Range
                </label>
                <select
                  value={filters.dateFilter}
                  onChange={(e) =>
                    setFilters({ ...filters, dateFilter: e.target.value })
                  }
                  className="w-full px-3 py-2 border rounded text-sm text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700"
                >
                  <option value="all">All Time</option>
                  <option value="hour">Last Hour</option>
                  <option value="day">Last Day</option>
                  <option value="week">Last Week</option>
                </select>
              </div>
            </div>
          </div>
        )}

        {/* Decision List */}
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"></div>
          </div>
        ) : (
          <div className="space-y-2">
            {filteredDecisions.length === 0 ? (
              <p className="text-gray-500 text-center py-8">
                No decisions match the current filters
              </p>
            ) : (
              filteredDecisions.map((decision) => (
                <div key={decision.id}>
                  <button
                    onClick={() =>
                      setExpandedId(
                        expandedId === decision.id ? null : decision.id
                      )
                    }
                    className="w-full text-left border rounded-lg p-3 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex-1 flex items-center space-x-3">
                        <div className="flex-1">
                          <div className="flex items-center space-x-2 mb-1">
                            <span className="font-medium text-gray-900 dark:text-gray-100">
                              {decision.device_name}
                            </span>
                            <Badge className={getStatusColor(decision.status) + ' text-white text-xs'}>
                              {decision.status.toUpperCase()}
                            </Badge>
                            <Badge className={getEscalationColor(decision.escalation_level) + ' text-white text-xs'}>
                              Level {decision.escalation_level}
                            </Badge>
                          </div>
                          <div className="text-xs text-gray-500">
                            {decision.point_name}: {decision.current_value} → {decision.target_value}
                          </div>
                          <div className="text-xs text-gray-400 mt-1">
                            {new Date(decision.timestamp).toLocaleString()}
                          </div>
                        </div>
                      </div>
                      {expandedId === decision.id ? (
                        <ChevronUp className="h-5 w-5 text-gray-400" />
                      ) : (
                        <ChevronDown className="h-5 w-5 text-gray-400" />
                      )}
                    </div>
                  </button>

                  {/* Expanded Details */}
                  {expandedId === decision.id && (
                    <div className="border-l-2 border-r-2 border-b-2 border-gray-200 dark:border-gray-700 p-4 ml-4 bg-gray-50 dark:bg-gray-800">
                      <div className="grid grid-cols-2 gap-4 text-sm">
                        <div>
                          <div className="text-gray-500 text-xs uppercase tracking-wider mb-1">
                            Safety Score
                          </div>
                          <div className="font-semibold text-gray-900 dark:text-gray-100">
                            {decision.safety_score}
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-500 text-xs uppercase tracking-wider mb-1">
                            Execution Time
                          </div>
                          <div className="font-semibold text-gray-900 dark:text-gray-100">
                            {decision.execution_time_ms}ms
                          </div>
                        </div>
                      </div>

                      {decision.decision_rationale && (
                        <div className="mt-3">
                          <div className="text-gray-500 text-xs uppercase tracking-wider mb-1">
                            Rationale
                          </div>
                          <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
                            {decision.decision_rationale}
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </Card>
    </div>
  );
};
