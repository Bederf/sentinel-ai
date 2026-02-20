/**
 * FireEquipmentPanel Component Tests
 *
 * Tests for fire equipment listing, inspection scheduling, and status badges.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { FireEquipmentPanel } from '../FireEquipmentPanel'
import * as complianceApi from '@/lib/api/compliance'

vi.mock('@tremor/react', async () => {
  const { createTremorMocks } = await import('@/test-utils/mockTremor')
  return {
    ...createTremorMocks(),
    Title: ({ children, ...props }: any) =>
      React.createElement('h3', { 'data-testid': 'title', ...props }, children),
    Text: ({ children, ...props }: any) =>
      React.createElement('span', { 'data-testid': 'text', ...props }, children),
    Button: ({ children, onClick, size, ...props }: any) =>
      React.createElement('button', { onClick, ...props }, children),
    Table: ({ children, ...props }: any) =>
      React.createElement('table', props, children),
    TableHead: ({ children }: any) =>
      React.createElement('thead', null, children),
    TableBody: ({ children }: any) =>
      React.createElement('tbody', null, children),
    TableRow: ({ children }: any) =>
      React.createElement('tr', null, children),
    TableHeaderCell: ({ children }: any) =>
      React.createElement('th', null, children),
    TableCell: ({ children, ...props }: any) =>
      React.createElement('td', props, children),
  }
})

vi.mock('@/lib/api/compliance')

describe('FireEquipmentPanel', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    // Default mock for mutation hook so destructuring doesn't fail
    vi.mocked(complianceApi.useScheduleFireInspection).mockReturnValue({
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
    } as any)
  })

  const renderComponent = () => {
    return render(
      <QueryClientProvider client={queryClient}>
        <FireEquipmentPanel siteCode="S002" />
      </QueryClientProvider>
    )
  }

  it('renders fire equipment panel title', () => {
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

    renderComponent()
    expect(screen.getByText(/Fire Equipment Inventory/i)).toBeInTheDocument()
  })

  it('displays equipment with OK status when inspection is current', async () => {
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

    renderComponent()

    await waitFor(() => {
      expect(screen.getByText('extinguisher')).toBeInTheDocument()
      expect(screen.getByText('Zone B1 - Basement')).toBeInTheDocument()
      expect(screen.getByText('OK')).toBeInTheDocument()
    })
  })

  it('shows DUE SOON badge for inspections within 30 days', async () => {
    vi.mocked(complianceApi.useFireEquipment).mockReturnValue({
      data: [
        {
          id: 'equip-002',
          site_code: 'S002',
          equipment_type: 'hose_reel',
          location_description: 'Zone 101',
          last_inspection_date: new Date(Date.now() - 350 * 24 * 60 * 60 * 1000).toISOString(),
          next_inspection_date: new Date(Date.now() + 15 * 24 * 60 * 60 * 1000).toISOString(),
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

    renderComponent()

    await waitFor(() => {
      expect(screen.getByText('DUE SOON')).toBeInTheDocument()
    })
  })

  it('shows OVERDUE badge for past due inspections', async () => {
    vi.mocked(complianceApi.useFireEquipment).mockReturnValue({
      data: [
        {
          id: 'equip-003',
          site_code: 'S002',
          equipment_type: 'hydrant',
          location_description: 'Zone 200',
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

    renderComponent()

    await waitFor(() => {
      expect(screen.getByText('OVERDUE')).toBeInTheDocument()
    })
  })

  it('allows scheduling new inspection', async () => {
    const user = userEvent.setup()
    const scheduleMock = vi.fn()

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

    renderComponent()

    const scheduleButton = screen.getByRole('button', { name: /Schedule/i })
    await user.click(scheduleButton)

    expect(scheduleMock).toHaveBeenCalled()
  })

  it('shows no equipment message when list is empty', async () => {
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

    renderComponent()

    await waitFor(() => {
      expect(screen.getByText(/No fire equipment configured/i)).toBeInTheDocument()
    })
  })

  it('shows loading state', () => {
    vi.mocked(complianceApi.useFireEquipment).mockReturnValue({
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

    renderComponent()

    expect(screen.getByText(/Loading fire equipment/i)).toBeInTheDocument()
  })
})
