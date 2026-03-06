/**
 * Security Module API Client
 *
 * Provides access to security monitoring, access control, visitor management, and alerts.
 * Includes React Query hooks for automatic caching and real-time updates.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { authorizedFetch, API_BASE_URL } from './client';

// ============================================================================
// Type Interfaces
// ============================================================================

export interface AccessEvent {
  event_id: string;
  timestamp: string;
  access_point_id: string;
  card_id: string;
  person_name: string;
  status: 'granted' | 'denied' | 'timeout' | 'error';
  access_type: 'badge' | 'code' | 'override' | 'biometric' | 'manual';
  location: string;
  duration_seconds?: number;
}

export interface AccessPoint {
  point_id: string;
  site_id: string;
  zone: string;
  location: string;
  device_type: 'reader' | 'lock' | 'sensor' | 'controller';
  status: 'active' | 'inactive' | 'alarm' | 'maintenance';
  last_activity?: string;
}

export interface Visitor {
  visitor_id: string;
  name: string;
  company: string;
  visit_date: string;
  host_contact: string;
  access_points: string[];
  status: 'pending' | 'checked_in' | 'checked_out' | 'revoked';
  checkin_time?: string;
  checkout_time?: string;
  purpose?: string;
}

export interface SecurityAlert {
  alert_id: string;
  alert_type: 'forced_entry' | 'tailgating' | 'after_hours' | 'override' | 'card_revoked' | 'multiple_attempts' | 'unauthorized_access';
  timestamp: string;
  location: string;
  site_id: string;
  severity: 'critical' | 'warning' | 'info';
  status: 'open' | 'acknowledged' | 'resolved';
  description: string;
  related_events: string[];
  acknowledged_by?: string;
  acknowledged_at?: string;
  resolved_at?: string;
}

export interface SecurityOverview {
  total_access_events_today: number;
  active_visitors: number;
  open_alerts: number;
  after_hours_access_count: number;
  system_status: 'online' | 'polling' | 'offline';
  last_updated: string;
}

export interface OccupancyData {
  total_occupancy: number;
  by_floor: Record<string, number>;
  by_zone: Record<string, number>;
  last_updated: string;
}

export interface EventsResponse {
  site: string;
  event_count: number;
  events: AccessEvent[];
}

export interface AlertsResponse {
  site: string;
  alert_count: number;
  alerts: SecurityAlert[];
}

// ============================================================================
// API Client Methods
// ============================================================================

export const securityApi = {
  /**
   * Get security overview for a building
   */
  getOverview: async (site: string): Promise<SecurityOverview> => {
    const response = await authorizedFetch(
      `${API_BASE_URL}/api/security/overview?site=${encodeURIComponent(site)}`
    );
    return response.json();
  },

  /**
   * Get paginated access events with optional filtering
   */
  getEvents: async (
    site: string,
    filters?: { after_hours?: boolean; location?: string; limit?: number }
  ): Promise<EventsResponse> => {
    const params = new URLSearchParams({ site });
    if (filters?.after_hours) params.append('after_hours', 'true');
    if (filters?.location) params.append('location', filters.location);
    if (filters?.limit) params.append('limit', filters.limit.toString());

    const response = await authorizedFetch(
      `${API_BASE_URL}/api/security/events?${params}`
    );
    return response.json();
  },

  /**
   * Get single access event by ID
   */
  getEventById: async (eventId: string): Promise<AccessEvent> => {
    const response = await authorizedFetch(
      `${API_BASE_URL}/api/security/events/${encodeURIComponent(eventId)}`
    );
    return response.json();
  },

  /**
   * Record access event from access control system
   */
  recordEvent: async (site: string, data: {
    access_point_id: string;
    card_id: string;
    person_name: string;
    status: string;
    access_type: string;
    location: string;
  }): Promise<{ event_id: string; status: string }> => {
    const response = await authorizedFetch(
      `${API_BASE_URL}/api/security/events?site=${encodeURIComponent(site)}`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
    return response.json();
  },

  /**
   * Get all access control points for a site
   */
  getAccessPoints: async (site: string): Promise<{ site: string; point_count: number; access_points: AccessPoint[] }> => {
    const response = await authorizedFetch(
      `${API_BASE_URL}/api/security/access-points?site=${encodeURIComponent(site)}`
    );
    return response.json();
  },

  /**
   * Get single access point details with recent events
   */
  getAccessPointDetails: async (pointId: string): Promise<{ point: AccessPoint; recent_events: AccessEvent[] }> => {
    const response = await authorizedFetch(
      `${API_BASE_URL}/api/security/access-points/${encodeURIComponent(pointId)}`
    );
    return response.json();
  },

  /**
   * Get list of active visitors
   */
  getVisitors: async (site: string, limit = 50): Promise<{ site: string; visitor_count: number; visitors: Visitor[] }> => {
    const response = await authorizedFetch(
      `${API_BASE_URL}/api/security/visitors?site=${encodeURIComponent(site)}&limit=${limit}`
    );
    return response.json();
  },

  /**
   * Register new visitor
   */
  registerVisitor: async (site: string, data: {
    name: string;
    company: string;
    host_contact: string;
    access_points: string[];
    purpose: string;
  }): Promise<{ visitor_id: string; status: string; name: string }> => {
    const response = await authorizedFetch(
      `${API_BASE_URL}/api/security/visitors?site=${encodeURIComponent(site)}`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
    return response.json();
  },

  /**
   * Record visitor check-in
   */
  checkInVisitor: async (visitorId: string): Promise<{ visitor_id: string; status: string }> => {
    const response = await authorizedFetch(
      `${API_BASE_URL}/api/security/visitors/${encodeURIComponent(visitorId)}/checkin`,
      { method: 'POST' }
    );
    return response.json();
  },

  /**
   * Record visitor check-out
   */
  checkOutVisitor: async (visitorId: string): Promise<{ visitor_id: string; status: string }> => {
    const response = await authorizedFetch(
      `${API_BASE_URL}/api/security/visitors/${encodeURIComponent(visitorId)}/checkout`,
      { method: 'POST' }
    );
    return response.json();
  },

  /**
   * Revoke visitor access immediately
   */
  revokeVisitor: async (visitorId: string): Promise<{ visitor_id: string; status: string }> => {
    const response = await authorizedFetch(
      `${API_BASE_URL}/api/security/visitors/${encodeURIComponent(visitorId)}/revoke`,
      { method: 'PUT' }
    );
    return response.json();
  },

  /**
   * Get security alerts with optional filtering
   */
  getAlerts: async (
    site: string,
    filters?: { severity?: string; limit?: number }
  ): Promise<AlertsResponse> => {
    const params = new URLSearchParams({ site });
    if (filters?.severity) params.append('severity', filters.severity);
    if (filters?.limit) params.append('limit', filters.limit.toString());

    const response = await authorizedFetch(
      `${API_BASE_URL}/api/security/alerts?${params}`
    );
    return response.json();
  },

  /**
   * Create security alert
   */
  createAlert: async (data: {
    alert_type: string;
    location: string;
    site_id: string;
    severity: string;
    description: string;
  }): Promise<{ alert_id: string; status: string }> => {
    const response = await authorizedFetch(
      `${API_BASE_URL}/api/security/alerts`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
    return response.json();
  },

  /**
   * Acknowledge an alert
   */
  acknowledgeAlert: async (alertId: string, acknowledgedBy: string): Promise<{ alert_id: string; status: string }> => {
    const response = await authorizedFetch(
      `${API_BASE_URL}/api/security/alerts/${encodeURIComponent(alertId)}/acknowledge?acknowledged_by=${encodeURIComponent(acknowledgedBy)}`,
      { method: 'PUT' }
    );
    return response.json();
  },

  /**
   * Get current building occupancy
   */
  getOccupancy: async (site: string): Promise<OccupancyData> => {
    const response = await authorizedFetch(
      `${API_BASE_URL}/api/security/occupancy?site=${encodeURIComponent(site)}`
    );
    return response.json();
  },
};

// ============================================================================
// React Query Hooks
// ============================================================================

/**
 * Hook to fetch security overview
 * Stale time: 30s (status updates regularly)
 */
export const useSecurityOverview = (site: string) => {
  return useQuery({
    queryKey: ['security', 'overview', site],
    queryFn: () => securityApi.getOverview(site),
    staleTime: 30000,
    refetchInterval: 30000,
  });
};

/**
 * Hook to fetch access events with filters
 * Stale time: 15s (real-time events)
 */
export const useAccessEvents = (
  site: string,
  filters?: { after_hours?: boolean; location?: string; limit?: number }
) => {
  return useQuery({
    queryKey: ['security', 'events', site, filters],
    queryFn: () => securityApi.getEvents(site, filters),
    staleTime: 15000,
    refetchInterval: 15000,
  });
};

/**
 * Hook to fetch access control points
 * Stale time: 5m (rarely changes)
 */
export const useAccessPoints = (site: string) => {
  return useQuery({
    queryKey: ['security', 'access-points', site],
    queryFn: () => securityApi.getAccessPoints(site),
    staleTime: 300000,
  });
};

/**
 * Hook to fetch active visitors
 * Stale time: 30s (check-in/out updates)
 */
export const useVisitors = (site: string, limit = 50) => {
  return useQuery({
    queryKey: ['security', 'visitors', site, limit],
    queryFn: () => securityApi.getVisitors(site, limit),
    staleTime: 30000,
    refetchInterval: 30000,
  });
};

/**
 * Hook to fetch security alerts
 * Stale time: 15s (real-time alerts)
 */
export const useSecurityAlerts = (
  site: string,
  filters?: { severity?: string; limit?: number }
) => {
  return useQuery({
    queryKey: ['security', 'alerts', site, filters],
    queryFn: () => securityApi.getAlerts(site, filters),
    staleTime: 15000,
    refetchInterval: 15000,
  });
};

/**
 * Hook to fetch building occupancy
 * Stale time: 15s (real-time occupancy)
 */
export const useOccupancy = (site: string) => {
  return useQuery({
    queryKey: ['security', 'occupancy', site],
    queryFn: () => securityApi.getOccupancy(site),
    staleTime: 15000,
    refetchInterval: 15000,
  });
};

/**
 * Mutation hook for registering visitor
 */
export const useRegisterVisitor = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ site, data }: {
      site: string;
      data: Parameters<typeof securityApi.registerVisitor>[1];
    }) => securityApi.registerVisitor(site, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['security', 'visitors'] });
    },
  });
};

/**
 * Mutation hook for visitor check-in
 */
export const useCheckInVisitor = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: securityApi.checkInVisitor,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['security', 'visitors'] });
      queryClient.invalidateQueries({ queryKey: ['security', 'occupancy'] });
    },
  });
};

/**
 * Mutation hook for visitor check-out
 */
export const useCheckOutVisitor = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: securityApi.checkOutVisitor,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['security', 'visitors'] });
      queryClient.invalidateQueries({ queryKey: ['security', 'occupancy'] });
    },
  });
};

/**
 * Mutation hook for acknowledging alert
 */
export const useAcknowledgeAlert = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ alertId, acknowledgedBy }: { alertId: string; acknowledgedBy: string }) =>
      securityApi.acknowledgeAlert(alertId, acknowledgedBy),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['security', 'alerts'] });
      queryClient.invalidateQueries({ queryKey: ['security', 'overview'] });
    },
  });
};
