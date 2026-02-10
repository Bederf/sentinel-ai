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
import { Card, Badge, Button } from '@tremor/react';
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
      <Card className="animate-pulse">
        <div className="h-8 bg-gray-200 rounded w-1/3 mb-4"></div>
        <div className="space-y-3">
          <div className="h-16 bg-gray-200 rounded"></div>
          <div className="h-16 bg-gray-200 rounded"></div>
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <div className="flex items-center gap-2 text-red-600">
          <AlertTriangle className="h-5 w-5" />
          <span>{error}</span>
        </div>
      </Card>
    );
  }

  return (
    <div className={`space-y-4 ${compact ? '' : 'pb-6'}`}>
      {/* Quick Stats */}
      <div className="grid grid-cols-3 gap-2">
        <Card className="p-3">
          <div className="text-center">
            <Calendar className="mx-auto h-5 w-5 text-blue-500" />
            <p className="mt-1 text-xl font-semibold">{schedule.length}</p>
            <p className="text-xs text-gray-500">Scheduled</p>
          </div>
        </Card>
        <Card className="p-3">
          <div className="text-center">
            <CheckCircle className="mx-auto h-5 w-5 text-green-500" />
            <p className="mt-1 text-xl font-semibold">{completedCount}</p>
            <p className="text-xs text-gray-500">Completed</p>
          </div>
        </Card>
        <Card className="p-3">
          <div className="text-center">
            <AlertTriangle className="mx-auto h-5 w-5 text-amber-500" />
            <p className="mt-1 text-xl font-semibold">{deficiencyCount}</p>
            <p className="text-xs text-gray-500">Deficiencies</p>
          </div>
        </Card>
      </div>

      {/* Overdue Alert */}
      {overdueCount > 0 && (
        <Card className="bg-red-50 border-red-200">
          <div className="flex items-center gap-2 text-red-700">
            <AlertTriangle className="h-5 w-5" />
            <span className="font-medium">
              {overdueCount} overdue inspection{overdueCount > 1 ? 's' : ''}
            </span>
          </div>
        </Card>
      )}

      {/* Upcoming Schedule */}
      <Card>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-gray-900">Upcoming Inspections</h3>
          <Badge color="blue">{schedule.length}</Badge>
        </div>

        {schedule.length === 0 ? (
          <p className="text-sm text-gray-500 py-4 text-center">
            No inspections scheduled
          </p>
        ) : (
          <div className="space-y-2">
            {schedule.slice(0, compact ? 3 : 5).map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between p-2 bg-gray-50 rounded-lg"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">
                    {item.schedule_name}
                  </p>
                  <div className="flex items-center gap-2 text-xs text-gray-500">
                    <Clock className="h-3 w-3" />
                    <span>Due: {formatDate(item.next_due_date)}</span>
                    <span className="text-gray-300">|</span>
                    <span>{item.duration_minutes}min</span>
                  </div>
                </div>
                <Badge color={getPriorityColor(item.priority)} size="xs">
                  {item.priority}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Recent History */}
      {!compact && history.length > 0 && (
        <Card>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-gray-900">Recent Inspections</h3>
            <Badge color="gray">{history.length}</Badge>
          </div>

          <div className="space-y-2">
            {history.slice(0, 5).map((task) => (
              <div
                key={task.id}
                className="flex items-center justify-between p-2 bg-gray-50 rounded-lg"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">
                    {task.task_name}
                  </p>
                  <p className="text-xs text-gray-500">
                    {formatDate(task.completed_date || task.due_date)}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {task.deficiencies_found && task.deficiencies_found > 0 && (
                    <Badge color="red" size="xs">
                      {task.deficiencies_found} issues
                    </Badge>
                  )}
                  <Badge color={getStatusColor(task.status)} size="xs">
                    {task.status}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Start Inspection Button */}
      {equipmentId && onStartInspection && (
        <Button
          size="lg"
          className="w-full"
          onClick={() => onStartInspection(equipmentId)}
        >
          <ClipboardList className="h-5 w-5 mr-2" />
          Start Inspection
          <ChevronRight className="h-5 w-5 ml-2" />
        </Button>
      )}
    </div>
  );
}
