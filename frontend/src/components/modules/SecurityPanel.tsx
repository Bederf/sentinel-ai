import { useContext, useState } from 'react';
import type { ReactElement } from 'react';

import {
  Lock,
  Users,
  AlertTriangle,
  Clock,
  CheckCircle,
  XCircle,
  Shield,
} from 'lucide-react';
import {
  useSecurityOverview,
  useAccessEvents,
  useAccessPoints,
  useVisitors,
  useSecurityAlerts,
  useCheckInVisitor,
  useCheckOutVisitor,
  useAcknowledgeAlert,
  type AccessEvent,
  type SecurityAlert,
  type Visitor,
  type AccessPoint,
} from '@/lib/api/index';
import { ModuleContext } from '@/contexts/moduleContextStore';
import { Badge } from '../Badge';
import { TabBar } from '../TabBar';
import type { TabDef } from '../TabBar';

interface SecurityPanelProps {
  siteId?: string;
}

export function SecurityPanel({ siteId: propSiteId }: SecurityPanelProps): ReactElement {
  const moduleContext = useContext(ModuleContext);
  const [selectedSiteId] = useState<string>(propSiteId || moduleContext?.siteId || '');
  const [activeTab, setActiveTab] = useState<string>('overview');

  const overviewQuery = useSecurityOverview(selectedSiteId);
  const eventsQuery = useAccessEvents(selectedSiteId);
  const pointsQuery = useAccessPoints(selectedSiteId);
  const visitorsQuery = useVisitors(selectedSiteId);
  const alertsQuery = useSecurityAlerts(selectedSiteId);

  const checkInMutation = useCheckInVisitor();
  const checkOutMutation = useCheckOutVisitor();
  const acknowledgeMutation = useAcknowledgeAlert();

  const overview = overviewQuery.data;
  const events = eventsQuery.data?.events || [];
  const points = pointsQuery.data?.access_points || [];
  const visitors = visitorsQuery.data?.visitors || [];
  const alerts = alertsQuery.data?.alerts || [];

  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const _formatDate = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleDateString();
  };

  const severityColor = (severity: string) => {
    switch (severity) {
      case 'critical':
        return { background: 'rgba(220,38,38,0.15)', color: 'var(--color-sentinel-red)' };
      case 'warning':
        return { background: 'rgba(234,179,8,0.15)', color: 'var(--color-sentinel-amber)' };
      default:
        return { background: 'rgba(59,130,246,0.15)', color: 'var(--color-sentinel-blue)' };
    }
  };

  const accessStatusColor = (status: string) => {
    return status === 'granted'
      ? { background: 'rgba(16,185,129,0.15)', color: 'var(--color-sentinel-green)' }
      : { background: 'rgba(220,38,38,0.15)', color: 'var(--color-sentinel-red)' };
  };

  const getPointStatusIcon = (status: string) => {
    switch (status) {
      case 'active':
        return <CheckCircle className="h-5 w-5 text-green-500" />;
      case 'alarm':
        return <AlertTriangle className="h-5 w-5 text-red-500" />;
      case 'inactive':
        return <XCircle className="h-5 w-5 text-gray-500" />;
      default:
        return <Shield className="h-5 w-5 text-blue-500" />;
    }
  };

  const tabDefs: TabDef[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'access', label: 'Access' },
    { id: 'visitors', label: 'Visitors' },
    { id: 'alerts', label: 'Alerts' },
    { id: 'points', label: 'Points' },
  ];

  return (
    <div className="space-y-6">
      {overview && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Access Events Today</p>
                <div className="text-3xl font-semibold tabular-nums" style={{ color: 'var(--color-sentinel-text-primary)' }}>{overview.total_access_events_today}</div>
              </div>
              <Clock className="h-8 w-8 text-blue-500" />
            </div>
          </div>

          <div className="rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Active Visitors</p>
                <div className="text-3xl font-semibold tabular-nums" style={{ color: 'var(--color-sentinel-text-primary)' }}>{overview.active_visitors}</div>
              </div>
              <Users className="h-8 w-8 text-green-500" />
            </div>
          </div>

          <div className="rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Open Alerts</p>
                <div className="text-3xl font-semibold tabular-nums" style={{ color: 'var(--color-sentinel-text-primary)' }}>{overview.open_alerts}</div>
              </div>
              <AlertTriangle className="h-8 w-8 text-red-500" />
            </div>
          </div>

          <div className="rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>After-Hours Access</p>
                <div className="text-3xl font-semibold tabular-nums" style={{ color: 'var(--color-sentinel-text-primary)' }}>{overview.after_hours_access_count}</div>
              </div>
              <Lock className="h-8 w-8 text-yellow-500" />
            </div>
          </div>
        </div>
      )}

      <div className="rounded-lg" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
        <TabBar tabs={tabDefs} active={activeTab} onChange={setActiveTab} />

        {activeTab === 'overview' && (
          <div className="p-4 space-y-4">
            <h3 className="text-lg font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>Security Status Summary</h3>
            {overview && (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-2 gap-4">
                <div className="rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
                  <p style={{ color: 'var(--color-sentinel-text-secondary)' }}>System Status</p>
                  <div className="flex items-center justify-between mt-2">
                    <Badge className="capitalize">{overview.system_status}</Badge>
                    <CheckCircle className="h-5 w-5 text-green-500" />
                  </div>
                </div>
                <div className="rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
                  <p style={{ color: 'var(--color-sentinel-text-secondary)' }}>Last Updated</p>
                  <p className="mt-2 text-sm font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                    {formatTime(overview.last_updated)}
                  </p>
                </div>
              </div>
            )}
            <div className="rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
              <p style={{ color: 'var(--color-sentinel-text-secondary)' }}>Alert Summary</p>
              <div className="mt-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>Open Alerts</span>
                  <Badge style={{ background: 'rgba(220,38,38,0.15)', color: 'var(--color-sentinel-red)' }}>{alerts.filter((a) => a.status === 'open').length}</Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>Acknowledged</span>
                  <Badge style={{ background: 'rgba(234,179,8,0.15)', color: 'var(--color-sentinel-amber)' }}>{alerts.filter((a) => a.status === 'acknowledged').length}</Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>Resolved</span>
                  <Badge style={{ background: 'rgba(16,185,129,0.15)', color: 'var(--color-sentinel-green)' }}>{alerts.filter((a) => a.status === 'resolved').length}</Badge>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'access' && (
          <div className="p-4 space-y-4">
            <h3 className="text-lg font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>Recent Access Events</h3>
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {events.length > 0 ? (
                events.slice(0, 20).map((event: AccessEvent) => (
                  <div key={event.event_id} className="rounded-lg p-3" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <div className="flex items-center justify-between">
                          <p className="font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>{event.person_name}</p>
                          <Badge className="capitalize" style={accessStatusColor(event.status)}>
                            {event.status}
                          </Badge>
                        </div>
                        <p className="mt-1 text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                          {event.location} &bull; {formatTime(event.timestamp)}
                        </p>
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-center py-6" style={{ color: 'var(--color-sentinel-text-secondary)' }}>No events recorded</p>
              )}
            </div>
          </div>
        )}

        {activeTab === 'visitors' && (
          <div className="p-4 space-y-4">
            <h3 className="text-lg font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>Visitor Management</h3>
            <div className="space-y-3 max-h-96 overflow-y-auto">
              {visitors.length > 0 ? (
                visitors.map((visitor: Visitor) => (
                  <div key={visitor.visitor_id} className="rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <p className="font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>{visitor.name}</p>
                        <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>{visitor.company}</p>
                        <p className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Host: {visitor.host_contact}</p>
                        {visitor.checkin_time && (
                          <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                            Check-in: {formatTime(visitor.checkin_time)}
                          </p>
                        )}
                        <Badge className="mt-2 capitalize">{visitor.status}</Badge>
                      </div>
                      <div className="flex flex-col items-end gap-2">
                        {visitor.status === 'pending' && (
                          <button
                            className="px-2 py-1 text-xs rounded font-medium"
                            style={{
                              background: 'rgba(16,185,129,0.15)',
                              color: 'var(--color-sentinel-green)',
                              border: '1px solid rgba(16,185,129,0.3)',
                            }}
                            onClick={() => checkInMutation.mutate(visitor.visitor_id)}
                            disabled={checkInMutation.isPending}
                          >
                            Check In
                          </button>
                        )}
                        {visitor.status === 'checked_in' && (
                          <button
                            className="px-2 py-1 text-xs rounded font-medium"
                            style={{
                              background: 'rgba(59,130,246,0.15)',
                              color: 'var(--color-sentinel-blue)',
                              border: '1px solid rgba(59,130,246,0.3)',
                            }}
                            onClick={() => checkOutMutation.mutate(visitor.visitor_id)}
                            disabled={checkOutMutation.isPending}
                          >
                            Check Out
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-center py-6" style={{ color: 'var(--color-sentinel-text-secondary)' }}>No active visitors</p>
              )}
            </div>
          </div>
        )}

        {activeTab === 'alerts' && (
          <div className="p-4 space-y-4">
            <h3 className="text-lg font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>Security Alerts</h3>
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {alerts.length > 0 ? (
                alerts.map((alert: SecurityAlert) => (
                  <div key={alert.alert_id} className="rounded-lg p-3" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center justify-between mb-2">
                          <p className="font-semibold capitalize" style={{ color: 'var(--color-sentinel-text-primary)' }}>{alert.alert_type.replace(/_/g, ' ')}</p>
                          <Badge className="capitalize" style={severityColor(alert.severity)}>
                            {alert.severity}
                          </Badge>
                        </div>
                        <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>{alert.description}</p>
                        <p className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                          {alert.location} &bull; {formatTime(alert.timestamp)}
                        </p>
                        <Badge className="mt-2 capitalize text-xs">{alert.status}</Badge>
                      </div>
                      {alert.status === 'open' && (
                        <button
                          className="px-2 py-1 text-xs rounded font-medium ml-2"
                          style={{
                            background: 'var(--color-sentinel-bg-secondary)',
                            color: 'var(--color-sentinel-text-primary)',
                            border: '1px solid var(--color-sentinel-border)',
                          }}
                          onClick={() =>
                            acknowledgeMutation.mutate({
                              alertId: alert.alert_id,
                              acknowledgedBy: 'Current User',
                            })
                          }
                          disabled={acknowledgeMutation.isPending}
                        >
                          Ack
                        </button>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-center py-6" style={{ color: 'var(--color-sentinel-text-secondary)' }}>No alerts</p>
              )}
            </div>
          </div>
        )}

        {activeTab === 'points' && (
          <div className="p-4 space-y-4">
            <h3 className="text-lg font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>Access Control Points</h3>
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {points.length > 0 ? (
                points.map((point: AccessPoint) => (
                  <div key={point.point_id} className="rounded-lg p-3" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <div className="flex items-center justify-between">
                          <p className="font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>{point.location}</p>
                          {getPointStatusIcon(point.status)}
                        </div>
                        <p className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                          Zone {point.zone} &bull; {point.device_type}
                        </p>
                        {point.last_activity && (
                          <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                            Last activity: {formatTime(point.last_activity)}
                          </p>
                        )}
                      </div>
                      <Badge className="capitalize">{point.status}</Badge>
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-center py-6" style={{ color: 'var(--color-sentinel-text-secondary)' }}>No access points configured</p>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
        <div className="flex items-center justify-between">
          <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            {overview?.system_status === 'online' ? (
              <>
                <CheckCircle className="inline h-4 w-4 text-green-500 mr-1" />
                Security system online and monitoring
              </>
            ) : (
              <>
                <AlertTriangle className="inline h-4 w-4 text-yellow-500 mr-1" />
                Security system in polling mode
              </>
            )}
          </p>
          {overview && <p className="text-xs" style={{ color: 'var(--color-sentinel-text-disabled)' }}>Last update: {formatTime(overview.last_updated)}</p>}
        </div>
      </div>
    </div>
  );
}
