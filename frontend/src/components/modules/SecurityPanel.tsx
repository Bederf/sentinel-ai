/**
 * SecurityPanel - Access Control & Security Monitoring Dashboard
 *
 * Integrated security monitoring with:
 * - Tab 1: Overview (cards showing events, visitors, alerts, after-hours access)
 * - Tab 2: Access Events (table with filtering by location/after-hours)
 * - Tab 3: Visitors (card view with check-in/out actions)
 * - Tab 4: Alerts (alert list with severity badges and acknowledge buttons)
 * - Tab 5: Access Points (list of readers, locks, sensors with status)
 */

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

interface SecurityPanelProps {
  siteId?: string;
}

export function SecurityPanel({ siteId: propSiteId }: SecurityPanelProps): ReactElement {
  const moduleContext = useContext(ModuleContext);
  const [selectedSiteId] = useState<string>(propSiteId || moduleContext?.siteId || '');
  const [activeTabIndex, setActiveTabIndex] = useState<number>(0);

  // Fetch data with React Query hooks
  const overviewQuery = useSecurityOverview(selectedSiteId);
  const eventsQuery = useAccessEvents(selectedSiteId);
  const pointsQuery = useAccessPoints(selectedSiteId);
  const visitorsQuery = useVisitors(selectedSiteId);
  const alertsQuery = useSecurityAlerts(selectedSiteId);

  // Mutations
  const checkInMutation = useCheckInVisitor();
  const checkOutMutation = useCheckOutVisitor();
  const acknowledgeMutation = useAcknowledgeAlert();

  const overview = overviewQuery.data;
  const events = eventsQuery.data?.events || [];
  const points = pointsQuery.data?.access_points || [];
  const visitors = visitorsQuery.data?.visitors || [];
  const alerts = alertsQuery.data?.alerts || [];

  // Helper to format time
  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const _formatDate = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleDateString();
  };

  // Severity color mapping
  const severityColor = (severity: string) => {
    switch (severity) {
      case 'critical':
        return 'red';
      case 'warning':
        return 'yellow';
      default:
        return 'blue';
    }
  };

  // Access status color
  const accessStatusColor = (status: string) => {
    return status === 'granted' ? 'green' : 'red';
  };

  // Point status icon
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

  return (
    <div className="space-y-6">
      {/* Quick Stats */}
      {overview && (
        <Grid className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card>
            <Flex alignItems="center" justifyContent="between">
              <div>
                <Text className="text-tremor-default">Access Events Today</Text>
                <Metric className="text-tremor-metric">{overview.total_access_events_today}</Metric>
              </div>
              <Clock className="h-8 w-8 text-blue-500" />
            </Flex>
          </Card>

          <Card>
            <Flex alignItems="center" justifyContent="between">
              <div>
                <Text className="text-tremor-default">Active Visitors</Text>
                <Metric className="text-tremor-metric">{overview.active_visitors}</Metric>
              </div>
              <Users className="h-8 w-8 text-green-500" />
            </Flex>
          </Card>

          <Card>
            <Flex alignItems="center" justifyContent="between">
              <div>
                <Text className="text-tremor-default">Open Alerts</Text>
                <Metric className="text-tremor-metric">{overview.open_alerts}</Metric>
              </div>
              <AlertTriangle className="h-8 w-8 text-red-500" />
            </Flex>
          </Card>

          <Card>
            <Flex alignItems="center" justifyContent="between">
              <div>
                <Text className="text-tremor-default">After-Hours Access</Text>
                <Metric className="text-tremor-metric">{overview.after_hours_access_count}</Metric>
              </div>
              <Lock className="h-8 w-8 text-yellow-500" />
            </Flex>
          </Card>
        </Grid>
      )}

      {/* Tabs */}
      <Card>
        <TabGroup index={activeTabIndex} onIndexChange={setActiveTabIndex}>
          <TabList className="mt-4 overflow-x-auto">
            <Tab>Overview</Tab>
            <Tab>Access</Tab>
            <Tab>Visitors</Tab>
            <Tab>Alerts</Tab>
            <Tab>Points</Tab>
          </TabList>

          <TabPanels>
            {/* Tab 1: Overview */}
            <TabPanel>
              <div className="mt-6 space-y-4">
                <Title>Security Status Summary</Title>
                {overview && (
                  <Grid className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-2 gap-4">
                    <Card>
                      <Text>System Status</Text>
                      <Flex alignItems="center" justifyContent="between" className="mt-2">
                        <Badge className="capitalize">{overview.system_status}</Badge>
                        <CheckCircle className="h-5 w-5 text-green-500" />
                      </Flex>
                    </Card>
                    <Card>
                      <Text>Last Updated</Text>
                      <Text className="mt-2 text-tremor-default font-semibold">
                        {formatTime(overview.last_updated)}
                      </Text>
                    </Card>
                  </Grid>
                )}
                <Card>
                  <Text>Alert Summary</Text>
                  <div className="mt-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm">Open Alerts</span>
                      <Badge color="red">{alerts.filter((a) => a.status === 'open').length}</Badge>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm">Acknowledged</span>
                      <Badge color="yellow">{alerts.filter((a) => a.status === 'acknowledged').length}</Badge>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm">Resolved</span>
                      <Badge color="green">{alerts.filter((a) => a.status === 'resolved').length}</Badge>
                    </div>
                  </div>
                </Card>
              </div>
            </TabPanel>

            {/* Tab 2: Access Events */}
            <TabPanel>
              <div className="mt-6 space-y-4">
                <Title>Recent Access Events</Title>
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {events.length > 0 ? (
                    events.slice(0, 20).map((event: AccessEvent) => (
                      <Card key={event.event_id} className="p-3">
                        <Flex alignItems="center" justifyContent="between">
                          <div className="flex-1">
                            <Flex alignItems="center" justifyContent="between">
                              <Text className="font-semibold">{event.person_name}</Text>
                              <Badge color={accessStatusColor(event.status)} className="capitalize">
                                {event.status}
                              </Badge>
                            </Flex>
                            <Text className="mt-1 text-xs text-gray-600">
                              {event.location} • {formatTime(event.timestamp)}
                            </Text>
                          </div>
                        </Flex>
                      </Card>
                    ))
                  ) : (
                    <Text className="text-center py-6 text-gray-500">No events recorded</Text>
                  )}
                </div>
              </div>
            </TabPanel>

            {/* Tab 3: Visitors */}
            <TabPanel>
              <div className="mt-6 space-y-4">
                <Title>Visitor Management</Title>
                <div className="space-y-3 max-h-96 overflow-y-auto">
                  {visitors.length > 0 ? (
                    visitors.map((visitor: Visitor) => (
                      <Card key={visitor.visitor_id} className="p-4">
                        <Flex alignItems="start" justifyContent="between">
                          <div className="flex-1">
                            <Text className="font-semibold">{visitor.name}</Text>
                            <Text className="text-xs text-gray-600">{visitor.company}</Text>
                            <Text className="text-xs text-gray-600 mt-1">Host: {visitor.host_contact}</Text>
                            {visitor.checkin_time && (
                              <Text className="text-xs text-gray-600">
                                Check-in: {formatTime(visitor.checkin_time)}
                              </Text>
                            )}
                            <Badge className="mt-2 capitalize">{visitor.status}</Badge>
                          </div>
                          <Flex flexDirection="col" alignItems="end" className="gap-2">
                            {visitor.status === 'pending' && (
                              <Button
                                size="xs"
                                color="green"
                                onClick={() => checkInMutation.mutate(visitor.visitor_id)}
                                loading={checkInMutation.isPending}
                              >
                                Check In
                              </Button>
                            )}
                            {visitor.status === 'checked_in' && (
                              <Button
                                size="xs"
                                color="blue"
                                onClick={() => checkOutMutation.mutate(visitor.visitor_id)}
                                loading={checkOutMutation.isPending}
                              >
                                Check Out
                              </Button>
                            )}
                          </Flex>
                        </Flex>
                      </Card>
                    ))
                  ) : (
                    <Text className="text-center py-6 text-gray-500">No active visitors</Text>
                  )}
                </div>
              </div>
            </TabPanel>

            {/* Tab 4: Alerts */}
            <TabPanel>
              <div className="mt-6 space-y-4">
                <Title>Security Alerts</Title>
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {alerts.length > 0 ? (
                    alerts.map((alert: SecurityAlert) => (
                      <Card key={alert.alert_id} className="p-3">
                        <Flex alignItems="start" justifyContent="between">
                          <div className="flex-1">
                            <Flex alignItems="center" justifyContent="between" className="mb-2">
                              <Text className="font-semibold capitalize">{alert.alert_type.replace(/_/g, ' ')}</Text>
                              <Badge color={severityColor(alert.severity)} className="capitalize">
                                {alert.severity}
                              </Badge>
                            </Flex>
                            <Text className="text-xs text-gray-600">{alert.description}</Text>
                            <Text className="text-xs text-gray-600 mt-1">
                              {alert.location} • {formatTime(alert.timestamp)}
                            </Text>
                            <Badge className="mt-2 capitalize text-xs">{alert.status}</Badge>
                          </div>
                          {alert.status === 'open' && (
                            <Button
                              size="xs"
                              color="gray"
                              onClick={() =>
                                acknowledgeMutation.mutate({
                                  alertId: alert.alert_id,
                                  acknowledgedBy: 'Current User',
                                })
                              }
                              loading={acknowledgeMutation.isPending}
                              className="ml-2"
                            >
                              Ack
                            </Button>
                          )}
                        </Flex>
                      </Card>
                    ))
                  ) : (
                    <Text className="text-center py-6 text-gray-500">No alerts</Text>
                  )}
                </div>
              </div>
            </TabPanel>

            {/* Tab 5: Access Points */}
            <TabPanel>
              <div className="mt-6 space-y-4">
                <Title>Access Control Points</Title>
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {points.length > 0 ? (
                    points.map((point: AccessPoint) => (
                      <Card key={point.point_id} className="p-3">
                        <Flex alignItems="center" justifyContent="between">
                          <div className="flex-1">
                            <Flex alignItems="center" justifyContent="between">
                              <Text className="font-semibold">{point.location}</Text>
                              {getPointStatusIcon(point.status)}
                            </Flex>
                            <Text className="text-xs text-gray-600 mt-1">
                              Zone {point.zone} • {point.device_type}
                            </Text>
                            {point.last_activity && (
                              <Text className="text-xs text-gray-600">
                                Last activity: {formatTime(point.last_activity)}
                              </Text>
                            )}
                          </div>
                          <Badge className="capitalize">{point.status}</Badge>
                        </Flex>
                      </Card>
                    ))
                  ) : (
                    <Text className="text-center py-6 text-gray-500">No access points configured</Text>
                  )}
                </div>
              </div>
            </TabPanel>
          </TabPanels>
        </TabGroup>
      </Card>

      {/* System Status Footer */}
      <Card>
        <Flex alignItems="center" justifyContent="between">
          <Text className="text-xs text-gray-600">
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
          </Text>
          {overview && <Text className="text-xs text-gray-500">Last update: {formatTime(overview.last_updated)}</Text>}
        </Flex>
      </Card>
    </div>
  );
}
