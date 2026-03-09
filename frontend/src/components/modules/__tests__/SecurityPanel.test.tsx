/**
 * SecurityPanel Component Tests
 *
 * Tests for security dashboard with tabs, data fetching, and mutations.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClientProvider, QueryClient } from '@tanstack/react-query';
import { SecurityPanel } from '../SecurityPanel';

// Mock the API - component imports from @/lib/api/index
vi.mock('@/lib/api/index', () => ({
  useSecurityOverview: vi.fn(),
  useAccessEvents: vi.fn(),
  useAccessPoints: vi.fn(),
  useVisitors: vi.fn(),
  useSecurityAlerts: vi.fn(),
  useCheckInVisitor: vi.fn(),
  useCheckOutVisitor: vi.fn(),
  useAcknowledgeAlert: vi.fn(),
}));

// Mock the ModuleContext
vi.mock('@/contexts/moduleContextStore', () => ({
  ModuleContext: {
    Consumer: ({ children }: any) => children(null),
    Provider: ({ children }: any) => children,
  },
}));

import {
  useSecurityOverview,
  useAccessEvents,
  useAccessPoints,
  useVisitors,
  useSecurityAlerts,
  useCheckInVisitor,
  useCheckOutVisitor,
  useAcknowledgeAlert,
} from '@/lib/api/index';

describe('SecurityPanel', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });

    // Mock all hooks
    vi.mocked(useSecurityOverview).mockReturnValue({
      data: {
        total_access_events_today: 15,
        active_visitors: 2,
        open_alerts: 1,
        after_hours_access_count: 3,
        system_status: 'online',
        last_updated: new Date().toISOString(),
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    } as any);

    vi.mocked(useAccessEvents).mockReturnValue({
      data: {
        site: 'site-002',
        event_count: 2,
        events: [
          {
            event_id: 'EVT-001',
            timestamp: new Date().toISOString(),
            access_point_id: 'AP-001',
            card_id: 'CARD-101',
            person_name: 'John Smith',
            status: 'granted',
            access_type: 'badge',
            location: 'Main Entrance',
          },
          {
            event_id: 'EVT-002',
            timestamp: new Date().toISOString(),
            access_point_id: 'AP-001',
            card_id: 'CARD-INVALID',
            person_name: 'Unknown',
            status: 'denied',
            access_type: 'code',
            location: 'Main Entrance',
          },
        ],
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    } as any);

    vi.mocked(useAccessPoints).mockReturnValue({
      data: {
        site: 'site-002',
        point_count: 2,
        access_points: [
          {
            point_id: 'AP-001',
            site_id: 'site-002',
            zone: 'L0',
            location: 'Main Entrance',
            device_type: 'reader',
            status: 'active',
            last_activity: new Date().toISOString(),
          },
        ],
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    } as any);

    vi.mocked(useVisitors).mockReturnValue({
      data: {
        site: 'site-002',
        visitor_count: 1,
        visitors: [
          {
            visitor_id: 'VIS-001',
            name: 'Alice Thompson',
            company: 'TechCorp',
            visit_date: new Date().toISOString(),
            host_contact: 'John Smith',
            access_points: ['AP-001'],
            status: 'checked_in',
            checkin_time: new Date().toISOString(),
          },
        ],
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    } as any);

    vi.mocked(useSecurityAlerts).mockReturnValue({
      data: {
        site: 'site-002',
        alert_count: 1,
        alerts: [
          {
            alert_id: 'ALT-001',
            alert_type: 'after_hours',
            timestamp: new Date().toISOString(),
            location: 'Server Room',
            site_id: 'site-002',
            severity: 'warning',
            status: 'open',
            description: 'After-hours access detected',
            related_events: [],
          },
        ],
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    } as any);

    vi.mocked(useCheckInVisitor).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as any);

    vi.mocked(useCheckOutVisitor).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as any);

    vi.mocked(useAcknowledgeAlert).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as any);
  });

  it('renders SecurityPanel with all tabs', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <SecurityPanel siteId="site-002" />
      </QueryClientProvider>
    );

    // Check for tab list
    const tablist = screen.getByRole('tablist');
    expect(tablist).toBeInTheDocument();

    // Check for all 5 tabs
    const tabs = screen.getAllByRole('tab');
    expect(tabs).toHaveLength(5);
    expect(tabs[0]).toHaveTextContent('Overview');
    expect(tabs[1]).toHaveTextContent('Access');
    expect(tabs[2]).toHaveTextContent('Visitors');
    expect(tabs[3]).toHaveTextContent('Alerts');
    expect(tabs[4]).toHaveTextContent('Points');
  });

  it('displays overview cards with correct data', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <SecurityPanel siteId="site-002" />
      </QueryClientProvider>
    );

    expect(screen.getByText('Access Events Today')).toBeInTheDocument();
    expect(screen.getByText('15')).toBeInTheDocument();
    expect(screen.getByText('Active Visitors')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    // "Open Alerts" appears both in quick stats and overview tab's alert summary
    expect(screen.getAllByText('Open Alerts').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('1').length).toBeGreaterThanOrEqual(1);
  });

  it('renders Access Events tab with event list', async () => {
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={queryClient}>
        <SecurityPanel siteId="site-002" />
      </QueryClientProvider>
    );

    // Click Access Events tab
    const tabs = screen.getAllByRole('tab');
    await user.click(tabs[1]);

    await waitFor(() => {
      expect(screen.getByText('John Smith')).toBeInTheDocument();
      expect(screen.getByText('Main Entrance')).toBeInTheDocument();
    });
  });

  it('renders Visitors tab with check-in/out buttons', async () => {
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={queryClient}>
        <SecurityPanel siteId="site-002" />
      </QueryClientProvider>
    );

    // Click Visitors tab
    const tabs = screen.getAllByRole('tab');
    await user.click(tabs[2]);

    await waitFor(() => {
      expect(screen.getByText('Alice Thompson')).toBeInTheDocument();
      expect(screen.getByText('TechCorp')).toBeInTheDocument();
      expect(screen.getByText('Check Out')).toBeInTheDocument();
    });
  });

  it('renders Alerts tab with severity badges', async () => {
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={queryClient}>
        <SecurityPanel siteId="site-002" />
      </QueryClientProvider>
    );

    // Click Alerts tab
    const tabs = screen.getAllByRole('tab');
    await user.click(tabs[3]);

    await waitFor(() => {
      // Component uses alert_type.replace(/_/g, ' ') -> "after hours" (CSS capitalize applies visually)
      expect(screen.getByText('after hours')).toBeInTheDocument();
      expect(screen.getByText('warning')).toBeInTheDocument();
    });
  });

  it('renders Access Points tab with point status', async () => {
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={queryClient}>
        <SecurityPanel siteId="site-002" />
      </QueryClientProvider>
    );

    // Click Access Points tab
    const tabs = screen.getAllByRole('tab');
    await user.click(tabs[4]);

    await waitFor(() => {
      expect(screen.getByText('Main Entrance')).toBeInTheDocument();
      expect(screen.getByText('active')).toBeInTheDocument();
    });
  });
});
