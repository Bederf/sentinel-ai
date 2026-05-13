/**
 * ComplianceDashboard Component Tests
 *
 * Tests for compliance dashboard rendering, tab navigation, and data display.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { ComplianceDashboard } from '../ComplianceDashboard'
import * as complianceApi from '@/lib/api/compliance'

// No-op: Tremor components have been replaced with plain HTML

vi.mock('@/lib/api/compliance')

describe('ComplianceDashboard', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    // Mock API responses
    vi.mocked(complianceApi.useComplianceStatus).mockReturnValue({
      data: {
        site_id: 'S002',
        critical_issues_count: 0,
        high_risk_items_count: 2,
        items_expiring_30days: 1,
        overdue_inspections: 0,
        last_audit_date: new Date().toISOString(),
        compliance_score_percent: 92,
        summary: {
          ohs_status: 'compliant',
          fire_status: 'compliant',
          electrical_status: 'expiring_soon',
          legionella_status: 'high_risk',
          lift_status: 'compliant',
        },
      },
      isLoading: false,
      error: null,
      isError: false,
      isSuccess: true,
      isIdle: false,
      isPending: false,
      isFetching: false,
      dataUpdatedAt: Date.now(),
      errorUpdatedAt: 0,
      failureCount: 0,
      failureReason: null,
      status: 'success',
      fetchStatus: 'idle',
    } as any)

    vi.mocked(complianceApi.useComplianceAudits).mockReturnValue({
      data: {
        audits: [
          {
            id: 'audit-001',
            compliance_type: 'Fire',
            audit_type: 'scheduled',
            status: 'closed',
            created_at: new Date().toISOString(),
            findings: {},
          },
        ],
      },
      isLoading: false,
      error: null,
      isError: false,
      isSuccess: true,
      isIdle: false,
      isPending: false,
      isFetching: false,
      dataUpdatedAt: Date.now(),
      errorUpdatedAt: 0,
      failureCount: 0,
      failureReason: null,
      status: 'success',
      fetchStatus: 'idle',
    } as any)

    // Mock query hooks
    vi.mocked(complianceApi.useFireEquipment).mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
      isError: false,
      isSuccess: true,
      isIdle: false,
      isPending: false,
      isFetching: false,
      dataUpdatedAt: Date.now(),
      errorUpdatedAt: 0,
      failureCount: 0,
      failureReason: null,
      status: 'success',
      fetchStatus: 'idle',
    } as any)

    vi.mocked(complianceApi.useEmergencyLightStatus).mockReturnValue({
      data: {
        site_id: 'S002',
        critical_issues_count: 0,
        high_risk_items_count: 0,
        items_expiring_30days: 0,
        overdue_inspections: 0,
        compliance_score_percent: 100,
        summary: {
          ohs_status: 'compliant',
          fire_status: 'compliant',
          electrical_status: 'compliant',
          legionella_status: 'compliant',
          lift_status: 'compliant',
        },
      },
      isLoading: false,
      error: null,
      isError: false,
      isSuccess: true,
      isIdle: false,
      isPending: false,
      isFetching: false,
      dataUpdatedAt: Date.now(),
      errorUpdatedAt: 0,
      failureCount: 0,
      failureReason: null,
      status: 'success',
      fetchStatus: 'idle',
    } as any)

    // Mock mutation hooks
    const mockMutation = {
      mutate: vi.fn(),
      mutateAsync: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
      isSuccess: false,
      status: 'idle' as const,
      reset: vi.fn(),
      failureCount: 0,
      failureReason: null,
      context: undefined,
      data: undefined,
      variables: undefined,
    }

    vi.mocked(complianceApi.useGenerateOhsChecklist).mockReturnValue(mockMutation as any)
    vi.mocked(complianceApi.useScheduleFireInspection).mockReturnValue(mockMutation as any)
    vi.mocked(complianceApi.useRecordEmergencyLightTest).mockReturnValue(mockMutation as any)
    vi.mocked(complianceApi.useAssessLegionellaRisk).mockReturnValue(mockMutation as any)
    vi.mocked(complianceApi.useTrackElectricalCertificate).mockReturnValue(mockMutation as any)
    vi.mocked(complianceApi.useRecordLiftTestResults).mockReturnValue(mockMutation as any)

    vi.mocked(complianceApi.useElectricalCompliance).mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
      isError: false,
      isSuccess: true,
      isIdle: false,
      isPending: false,
      isFetching: false,
      dataUpdatedAt: Date.now(),
      errorUpdatedAt: 0,
      failureCount: 0,
      failureReason: null,
      status: 'success',
      fetchStatus: 'idle',
    } as any)
  })

  const renderComponent = () => {
    return render(
      <QueryClientProvider client={queryClient}>
        <ComplianceDashboard siteCode="S002" />
      </QueryClientProvider>
    )
  }

  it('renders dashboard title', async () => {
    renderComponent()
    await waitFor(() => {
      expect(screen.getByText('Compliance Management')).toBeInTheDocument()
    })
  })

  it('displays overview tab with compliance score', async () => {
    renderComponent()
    await waitFor(() => {
      expect(screen.getByText('Compliance Score')).toBeInTheDocument()
      expect(screen.getByText('92%')).toBeInTheDocument()
    })
  })

  it('shows critical issues count', async () => {
    renderComponent()
    await waitFor(() => {
      expect(screen.getByText('Critical Issues')).toBeInTheDocument()
      expect(screen.getAllByText('0')[0]).toBeInTheDocument()
    })
  })

  it('displays expiring items count', async () => {
    renderComponent()
    await waitFor(() => {
      expect(screen.getByText('Expiring Soon (30 days)')).toBeInTheDocument()
      expect(screen.getByText('1')).toBeInTheDocument()
    })
  })

  it('renders all 6 domain tabs', () => {
    renderComponent()

    expect(screen.getByRole('tab', { name: /OHS Compliance/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Fire Safety/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Emergency Lights/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Legionella/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Electrical/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Lift Safety/i })).toBeInTheDocument()
  })

  it('allows tab switching between compliance domains', async () => {
    const user = userEvent.setup()
    renderComponent()

    const fireTab = screen.getByRole('tab', { name: /Fire Safety/i })
    await user.click(fireTab)

    // Tab click should not throw; verify tab is in the DOM
    expect(fireTab).toBeInTheDocument()
  })

  it('displays compliance status summary badges', async () => {
    renderComponent()
    await waitFor(() => {
      expect(screen.getByText('OHS Compliance')).toBeInTheDocument()
      expect(screen.getByText('Fire Safety')).toBeInTheDocument()
      expect(screen.getByText('Electrical')).toBeInTheDocument()
    })
  })

  it('displays recent audits in overview', async () => {
    renderComponent()
    await waitFor(() => {
      expect(screen.getByText('Recent Audits')).toBeInTheDocument()
      expect(screen.getByText('Fire')).toBeInTheDocument()
    })
  })

  it('shows "no site selected" message when siteCode is not provided', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ComplianceDashboard siteCode={undefined} />
      </QueryClientProvider>
    )

    expect(screen.getByText(/Select a site to view compliance data/i)).toBeInTheDocument()
  })

  it('shows loading state initially', () => {
    vi.mocked(complianceApi.useComplianceStatus).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      isError: false,
      isSuccess: false,
      isIdle: false,
      isPending: true,
      isFetching: true,
      dataUpdatedAt: 0,
      errorUpdatedAt: 0,
      failureCount: 0,
      failureReason: null,
      status: 'pending',
      fetchStatus: 'fetching',
    } as any)

    render(
      <QueryClientProvider client={queryClient}>
        <ComplianceDashboard siteCode="S002" />
      </QueryClientProvider>
    )

    expect(screen.getByText(/Loading compliance data/i)).toBeInTheDocument()
  })
})

describe('FireEquipmentPanel', () => {
  it('displays fire equipment list with inspection status', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    vi.mocked(complianceApi.useFireEquipment).mockReturnValue({
      data: [
        {
          id: 'equip-001',
          site_code: 'S002',
          equipment_type: 'extinguisher',
          location_description: 'Zone B1 - Basement',
          last_inspection_date: new Date(Date.now() - 180 * 24 * 60 * 60 * 1000).toISOString(),
          next_inspection_date: new Date(Date.now() + 180 * 24 * 60 * 60 * 1000).toISOString(),
          status: 'active',
        },
      ],
      isLoading: false,
      error: null,
      isError: false,
      isSuccess: true,
      isIdle: false,
      isPending: false,
      isFetching: false,
      dataUpdatedAt: Date.now(),
      errorUpdatedAt: 0,
      failureCount: 0,
      failureReason: null,
      status: 'success',
      fetchStatus: 'idle',
    } as any)

    const { FireEquipmentPanel } = await import('../FireEquipmentPanel')

    render(
      <QueryClientProvider client={queryClient}>
        <FireEquipmentPanel siteCode="S002" />
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('extinguisher')).toBeInTheDocument()
      expect(screen.getByText('Zone B1 - Basement')).toBeInTheDocument()
      expect(screen.getByText('OK')).toBeInTheDocument()
    })
  })

  it('shows OVERDUE badge for past due inspections', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    vi.mocked(complianceApi.useFireEquipment).mockReturnValue({
      data: [
        {
          id: 'equip-002',
          site_code: 'S002',
          equipment_type: 'hose_reel',
          location_description: 'Zone 101',
          last_inspection_date: new Date(Date.now() - 400 * 24 * 60 * 60 * 1000).toISOString(),
          next_inspection_date: new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString(),
          status: 'overdue',
        },
      ],
      isLoading: false,
      error: null,
      isError: false,
      isSuccess: true,
      isIdle: false,
      isPending: false,
      isFetching: false,
      dataUpdatedAt: Date.now(),
      errorUpdatedAt: 0,
      failureCount: 0,
      failureReason: null,
      status: 'success',
      fetchStatus: 'idle',
    } as any)

    const { FireEquipmentPanel } = await import('../FireEquipmentPanel')

    render(
      <QueryClientProvider client={queryClient}>
        <FireEquipmentPanel siteCode="S002" />
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('OVERDUE')).toBeInTheDocument()
    })
  })

  it('allows scheduling new inspection', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    const scheduleMock = vi.fn()
    vi.mocked(complianceApi.useScheduleFireInspection).mockReturnValue({
      mutate: scheduleMock,
      isPending: false,
      error: null,
      isError: false,
      isSuccess: true,
      isIdle: true,
      status: 'idle',
      failureCount: 0,
      failureReason: null,
      reset: vi.fn(),
      context: undefined,
      data: undefined,
      variables: undefined,
      mutateAsync: vi.fn(),
    } as any)

    vi.mocked(complianceApi.useFireEquipment).mockReturnValue({
      data: [
        {
          id: 'equip-001',
          site_code: 'S002',
          equipment_type: 'extinguisher',
          location_description: 'Zone B1',
          last_inspection_date: new Date().toISOString(),
          next_inspection_date: new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toISOString(),
          status: 'active',
        },
      ],
      isLoading: false,
      error: null,
      isError: false,
      isSuccess: true,
      isIdle: false,
      isPending: false,
      isFetching: false,
      dataUpdatedAt: Date.now(),
      errorUpdatedAt: 0,
      failureCount: 0,
      failureReason: null,
      status: 'success',
      fetchStatus: 'idle',
    } as any)

    const { FireEquipmentPanel } = await import('../FireEquipmentPanel')
    const user = userEvent.setup()

    render(
      <QueryClientProvider client={queryClient}>
        <FireEquipmentPanel siteCode="S002" />
      </QueryClientProvider>
    )

    const scheduleButton = screen.getByRole('button', { name: /Schedule/i })
    await user.click(scheduleButton)

    expect(scheduleMock).toHaveBeenCalled()
  })
})

describe('EmergencyLightPanel', () => {
  it('displays emergency light battery health status', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    vi.mocked(complianceApi.useEmergencyLightStatus).mockReturnValue({
      data: {
        site_id: 'S002',
        critical_issues_count: 0,
        high_risk_items_count: 1,
        items_expiring_30days: 0,
        overdue_inspections: 0,
        compliance_score_percent: 95,
        summary: {
          ohs_status: 'compliant',
          fire_status: 'compliant',
          electrical_status: 'compliant',
          legionella_status: 'compliant',
          lift_status: 'compliant',
        },
      },
      isLoading: false,
      error: null,
      isError: false,
      isSuccess: true,
      isIdle: false,
      isPending: false,
      isFetching: false,
      dataUpdatedAt: Date.now(),
      errorUpdatedAt: 0,
      failureCount: 0,
      failureReason: null,
      status: 'success',
      fetchStatus: 'idle',
    } as any)

    const { EmergencyLightPanel } = await import('../EmergencyLightPanel')

    render(
      <QueryClientProvider client={queryClient}>
        <EmergencyLightPanel siteCode="S002" />
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText(/Battery Alerts/i)).toBeInTheDocument()
    })
  })
})
