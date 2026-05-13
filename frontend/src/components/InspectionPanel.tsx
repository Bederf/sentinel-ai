/**
 * InspectionPanel - Dashboard view for inspection schedule and history
 *
 * Features:
 * - Quick stats cards (scheduled, completed, deficiencies)
 * - Upcoming inspection schedule list
 * - Recent inspection history
 * - Start inspection button
 *
 * Part of Phase 55: Routine Inspection & Maintenance
 */

import { useState, useEffect } from 'react';

import {
  Calendar,
  CheckCircle,
  AlertTriangle,
  Clock,
  ClipboardList,
  ChevronRight,
} from 'lucide-react';
import {
  inspectionApi,
  type InspectionScheduleItem,
  type InspectionTaskItem,
} from '@/lib/api';

interface InspectionPanelProps {
  equipmentId?: string;
  equipmentType?: string;  // Reserved for future template filtering
  onStartInspection?: (equipmentId: string) => void;
  compact?: boolean;
}

export default function InspectionPanel({
  equipmentId,
  equipmentType: _equipmentType,  // Reserved for future use
  onStartInspection,
  compact = false,
}: InspectionPanelProps) {
  const [schedule, setSchedule] = useState<InspectionScheduleItem[]>([]);
  const [history, setHistory] = useState<InspectionTaskItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      setError(null);

      try {
        const [scheduleData, historyData] = await Promise.all([
          inspectionApi.getSchedule({
            equipment_id: equipmentId,
            daysAhead: 30,
          }),
          equipmentId
            ? inspectionApi.getHistory(equipmentId, 12)
            : Promise.resolve([]),
        ]);
        setSchedule(scheduleData);
        setHistory(historyData);
      } catch (err) {
        console.error('Failed to load inspection data:', err);
        setError(err instanceof Error ? err.message : 'Failed to load data');
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, [equipmentId]);

  // Calculate stats
  const completedCount = history.filter((t) => t.status === 'completed').length;
  const deficiencyCount = history.reduce(
    (sum, t) => sum + (t.deficiencies_found || 0),
    0
  );
  const overdueCount = schedule.filter((s) => {
    if (!s.next_due_date) return false;
    return new Date(s.next_due_date) < new Date();
  }).length;

  // Get priority badge color
  const getPriorityColor = (priority: string): 'red' | 'yellow' | 'blue' | 'gray' => {
    switch (priority) {
      case 'urgent':
      case 'critical':
        return 'red';
      case 'high':
        return 'yellow';
      case 'normal':
        return 'blue';
      default:
        return 'gray';
    }
  };

  // Get status badge color
  const getStatusColor = (status: string): 'green' | 'yellow' | 'red' | 'gray' => {
    switch (status) {
      case 'completed':
        return 'green';
      case 'in_progress':
        return 'yellow';
      case 'overdue':
        return 'red';
      default:
        return 'gray';
    }
  };

  // Format date for display
  const formatDate = (dateStr: string | null | undefined): string => {
    if (!dateStr) return 'Not scheduled';
    const date = new Date(dateStr);
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);

    if (date.toDateString() === today.toDateString()) {
      return 'Today';
    }
    if (date.toDateString() === tomorrow.toDateString()) {
      return 'Tomorrow';
    }
    return date.toLocaleDateString('en-ZA', {
      day: 'numeric',
      month: 'short',
    });
  };

  if (loading) {
    return (
      <div className="rounded-lg p-4 animate-pulse" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
        <div className="h-8 bg-gray-200 rounded w-1/3 mb-4"></div>
        <div className="space-y-3">
          <div className="h-16 bg-gray-200 rounded"></div>
          <div className="h-16 bg-gray-200 rounded"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
        <div className="flex items-center gap-2" style={{ color: 'var(--color-sentinel-red)' }}>
          <AlertTriangle className="h-5 w-5" />
          <span>{error}</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`space-y-4 ${compact ? '' : 'pb-6'}`}>
      {/* Quick Stats */}
      <div className="grid grid-cols-3 gap-2">
        <div className="p-3 rounded-lg text-center" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
          <Calendar className="mx-auto h-5 w-5" style={{ color: 'var(--color-sentinel-blue)' }} />
          <p className="mt-1 text-xl font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>{schedule.length}</p>
          <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Scheduled</p>
        </div>
        <div className="p-3 rounded-lg text-center" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
          <CheckCircle className="mx-auto h-5 w-5" style={{ color: 'var(--color-sentinel-green)' }} />
          <p className="mt-1 text-xl font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>{completedCount}</p>
          <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Completed</p>
        </div>
        <div className="p-3 rounded-lg text-center" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
          <AlertTriangle className="mx-auto h-5 w-5" style={{ color: 'var(--color-sentinel-amber)' }} />
          <p className="mt-1 text-xl font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>{deficiencyCount}</p>
          <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Deficiencies</p>
        </div>
      </div>

      {/* Overdue Alert */}
      {overdueCount > 0 && (
        <div className="p-3 rounded-lg" style={{ background: 'rgba(220, 38, 38, 0.1)', border: '1px solid rgba(220, 38, 38, 0.3)' }}>
          <div className="flex items-center gap-2" style={{ color: 'var(--color-sentinel-red)' }}>
            <AlertTriangle className="h-5 w-5" />
            <span className="font-medium">
              {overdueCount} overdue inspection{overdueCount > 1 ? 's' : ''}
            </span>
          </div>
        </div>
      )}

      {/* Upcoming Schedule */}
      <div className="rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium" style={{ color: 'var(--color-sentinel-text-primary)' }}>Upcoming Inspections</h3>
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium" style={{ background: 'rgba(59, 130, 246, 0.15)', color: 'var(--color-sentinel-blue)' }}>{schedule.length}</span>
        </div>

        {schedule.length === 0 ? (
          <p className="text-sm py-4 text-center" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            No inspections scheduled
          </p>
        ) : (
          <div className="space-y-2">
            {schedule.slice(0, compact ? 3 : 5).map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between p-2 rounded-lg"
                style={{ background: 'var(--color-sentinel-bg-secondary)' }}
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                    {item.schedule_name}
                  </p>
                  <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                    <Clock className="h-3 w-3" />
                    <span>Due: {formatDate(item.next_due_date)}</span>
                    <span className="text-gray-300">|</span>
                    <span>{item.duration_minutes}min</span>
                  </div>
                </div>
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium" style={{
                  background: getPriorityColor(item.priority) === 'red' ? 'rgba(220, 38, 38, 0.15)' : getPriorityColor(item.priority) === 'yellow' ? 'rgba(245, 158, 11, 0.15)' : 'rgba(59, 130, 246, 0.15)',
                  color: getPriorityColor(item.priority) === 'red' ? 'var(--color-sentinel-red)' : getPriorityColor(item.priority) === 'yellow' ? 'var(--color-sentinel-amber)' : 'var(--color-sentinel-blue)',
                }}>
                  {item.priority}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recent History */}
      {!compact && history.length > 0 && (
        <div className="rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium" style={{ color: 'var(--color-sentinel-text-primary)' }}>Recent Inspections</h3>
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium" style={{ background: 'rgba(107, 114, 128, 0.15)', color: 'var(--color-sentinel-text-secondary)' }}>{history.length}</span>
          </div>

          <div className="space-y-2">
            {history.slice(0, 5).map((task) => (
              <div
                key={task.id}
                className="flex items-center justify-between p-2 rounded-lg"
                style={{ background: 'var(--color-sentinel-bg-secondary)' }}
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                    {task.task_name}
                  </p>
                  <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                    {formatDate(task.completed_date || task.due_date)}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {task.deficiencies_found && task.deficiencies_found > 0 && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium" style={{ background: 'rgba(220, 38, 38, 0.15)', color: 'var(--color-sentinel-red)' }}>
                      {task.deficiencies_found} issues
                    </span>
                  )}
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium" style={{
                    background: getStatusColor(task.status) === 'green' ? 'rgba(16, 185, 129, 0.15)' : getStatusColor(task.status) === 'yellow' ? 'rgba(245, 158, 11, 0.15)' : 'rgba(107, 114, 128, 0.15)',
                    color: getStatusColor(task.status) === 'green' ? 'var(--color-sentinel-green)' : getStatusColor(task.status) === 'yellow' ? 'var(--color-sentinel-amber)' : 'var(--color-sentinel-text-secondary)',
                  }}>
                    {task.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Start Inspection Button */}
      {equipmentId && onStartInspection && (
        <button
          className="w-full px-4 py-3 rounded-lg text-sm font-medium flex items-center justify-center transition-colors"
          style={{ background: 'var(--color-sentinel-blue)', color: '#fff', border: 'none', cursor: 'pointer' }}
          onClick={() => onStartInspection(equipmentId)}
        >
          <ClipboardList className="h-5 w-5 mr-2" />
          Start Inspection
          <ChevronRight className="h-5 w-5 ml-2" />
        </button>
      )}
    </div>
  );
}
