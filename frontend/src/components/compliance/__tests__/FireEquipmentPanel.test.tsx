/**
 * FireEquipmentPanel Component Tests
 *
 * Tests for fire equipment listing, inspection scheduling, and status badges.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { FireEquipmentPanel } from '../FireEquipmentPanel'
import * as complianceApi from '@/lib/api/compliance'

jest.mock('@/lib/api/compliance')

describe('FireEquipmentPanel', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })
  })

  const renderComponent = () => {
    return render(
      <QueryClientProvider client={queryClient}>
        <FireEquipmentPanel siteCode="S002" />
      </QueryClientProvider>
    )
  }

  it('renders fire equipment panel title', () => {
    jest.mocked(complianceApi.useFireEquipment).mockReturnValue({
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
    jest.mocked(complianceApi.useFireEquipment).mockReturnValue({
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
      expect(screen.getByText(/extinguisher/i)).toBeInTheDocument()
      expect(screen.getByText('Zone B1 - Basement')).toBeInTheDocument()
      expect(screen.getByText('OK')).toBeInTheDocument()
    })
  })

  it('shows DUE SOON badge for inspections within 30 days', async () => {
    jest.mocked(complianceApi.useFireEquipment).mockReturnValue({
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
    jest.mocked(complianceApi.useFireEquipment).mockReturnValue({
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
    const scheduleMock = jest.fn()

    jest.mocked(complianceApi.useFireEquipment).mockReturnValue({
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

    jest.mocked(complianceApi.useScheduleFireInspection).mockReturnValue({
      mutate: scheduleMock,
      isPending: false,
      error: null,
      isError: false,
      isSuccess: true,
      isIdle: true,
      status: 'idle',
      failureCount: 0,
      failureReason: null,
      reset: jest.fn(),
      context: undefined,
      data: undefined,
      variables: undefined,
      mutateAsync: jest.fn(),
    } as any)

    renderComponent()

    const scheduleButton = screen.getByRole('button', { name: /Schedule/i })
    await user.click(scheduleButton)

    expect(scheduleMock).toHaveBeenCalled()
  })

  it('shows no equipment message when list is empty', async () => {
    jest.mocked(complianceApi.useFireEquipment).mockReturnValue({
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
    jest.mocked(complianceApi.useFireEquipment).mockReturnValue({
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
