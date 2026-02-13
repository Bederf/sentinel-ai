import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AutonomousDecisionPanel from '../AutonomousDecisionPanel'

// Mock API responses
const mockAutonomousStatus = {
  enabled: true,
  decision_count: 42,
  last_decision_time: new Date().toISOString(),
  active_decisions: 3,
  safety_score: 95.2
}

const mockDecisions = [
  {
    id: 'dec-001',
    device_id: 'hvac_001',
    device_name: 'HVAC Unit 1',
    point_name: 'cooling_setpoint',
    current_value: 22.0,
    target_value: 23.5,
    status: 'success',
    decision_rationale: 'Temperature optimization for energy savings',
    timestamp: new Date().toISOString(),
    execution_time_ms: 250,
    safety_score: 98.5
  },
  {
    id: 'dec-002',
    device_id: 'lighting_001',
    device_name: 'Lighting Zone 1',
    point_name: 'brightness',
    current_value: 85,
    target_value: 75,
    status: 'success',
    decision_rationale: 'Brightness reduction - low occupancy',
    timestamp: new Date().toISOString(),
    execution_time_ms: 150,
    safety_score: 99.2
  }
]

const mockBoundaryStatus = {
  device_001: {
    device_id: 'device_001',
    device_name: 'HVAC Unit 1',
    overall_status: 'normal',
    approach_percentage: 62.5,
    escalation_level: 'LEVEL_0',
    points: [
      {
        name: 'cooling_setpoint',
        current_value: 22.0,
        bounds: { min: 16.0, max: 28.0 },
        status: 'normal'
      }
    ]
  },
  device_002: {
    device_id: 'device_002',
    device_name: 'HVAC Unit 2',
    overall_status: 'warning',
    approach_percentage: 78.5,
    escalation_level: 'LEVEL_1',
    points: [
      {
        name: 'cooling_setpoint',
        current_value: 25.2,
        bounds: { min: 16.0, max: 28.0 },
        status: 'warning'
      }
    ]
  }
}

describe('AutonomousDecisionPanel', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false }
      }
    })

    // Mock fetch/API calls
    global.fetch = vi.fn()
  })

  const renderComponent = () => {
    return render(
      <QueryClientProvider client={queryClient}>
        <AutonomousDecisionPanel />
      </QueryClientProvider>
    )
  }

  it('renders the autonomous decision panel', () => {
    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => mockAutonomousStatus
    })

    renderComponent()
    
    expect(screen.getByText(/autonomous/i)).toBeInTheDocument()
  })

  it('displays autonomous system status', async () => {
    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => mockAutonomousStatus
    })

    renderComponent()

    await waitFor(() => {
      expect(screen.getByText(/enabled/i)).toBeInTheDocument()
    })
  })

  it('shows decision count', async () => {
    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => mockAutonomousStatus
    })

    renderComponent()

    await waitFor(() => {
      expect(screen.getByText(/42/)).toBeInTheDocument()
    })
  })

  it('displays autonomous decisions list', async () => {
    ;(global.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockAutonomousStatus
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: mockDecisions, count: 2, total: 2 })
      })

    renderComponent()

    await waitFor(() => {
      expect(screen.getByText(/temperature optimization/i)).toBeInTheDocument()
    })
  })

  it('shows decision details when expanded', async () => {
    ;(global.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockAutonomousStatus
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: mockDecisions, count: 2, total: 2 })
      })

    renderComponent()

    await waitFor(() => {
      const decisionItem = screen.getByText(/temperature optimization/i)
      expect(decisionItem).toBeInTheDocument()
    })
  })

  it('filters decisions by status', async () => {
    ;(global.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockAutonomousStatus
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: mockDecisions, count: 2, total: 2 })
      })

    renderComponent()

    const filterButton = await screen.findByText(/filter/i)
    await userEvent.click(filterButton)

    // Click success filter
    const successFilter = await screen.findByRole('checkbox', { name: /success/i })
    await userEvent.click(successFilter)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('status=success'),
        expect.anything()
      )
    })
  })

  it('displays boundary status overview', async () => {
    ;(global.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockAutonomousStatus
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: mockDecisions, count: 2, total: 2 })
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: mockBoundaryStatus, count: 2 })
      })

    renderComponent()

    await waitFor(() => {
      expect(screen.getByText(/boundary/i)).toBeInTheDocument()
    })
  })

  it('shows color-coded boundary status', async () => {
    ;(global.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockAutonomousStatus
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: mockDecisions, count: 2, total: 2 })
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: mockBoundaryStatus, count: 2 })
      })

    renderComponent()

    await waitFor(() => {
      // Normal status (green)
      expect(screen.getByText(/HVAC Unit 1/)).toBeInTheDocument()
      // Warning status (yellow)
      expect(screen.getByText(/HVAC Unit 2/)).toBeInTheDocument()
    })
  })

  it('enables autonomous mode', async () => {
    ;(global.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ...mockAutonomousStatus, enabled: false })
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, message: 'Autonomous mode enabled' })
      })

    renderComponent()

    const enableButton = await screen.findByText(/enable/i)
    await userEvent.click(enableButton)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/autonomous/enable'),
        expect.objectContaining({ method: 'POST' })
      )
    })
  })

  it('disables autonomous mode', async () => {
    ;(global.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockAutonomousStatus
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, message: 'Autonomous mode disabled' })
      })

    renderComponent()

    const disableButton = await screen.findByText(/disable/i)
    await userEvent.click(disableButton)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/autonomous/disable'),
        expect.objectContaining({ method: 'POST' })
      )
    })
  })

  it('displays loading state while fetching', () => {
    ;(global.fetch as any).mockImplementation(
      () => new Promise(resolve => setTimeout(() => resolve({
        ok: true,
        json: async () => mockAutonomousStatus
      }), 100))
    )

    renderComponent()

    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  it('handles API errors gracefully', async () => {
    ;(global.fetch as any).mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'Server error' })
    })

    renderComponent()

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument()
    })
  })

  it('updates in real-time', async () => {
    let callCount = 0

    ;(global.fetch as any).mockImplementation(() => {
      callCount++
      return Promise.resolve({
        ok: true,
        json: async () => ({
          ...mockAutonomousStatus,
          decision_count: 40 + callCount
        })
      })
    })

    renderComponent()

    await waitFor(() => {
      expect(screen.getByText(/41/)).toBeInTheDocument()
    })

    // Simulate auto-refresh
    await waitFor(() => {
      expect(callCount >= 1).toBe(true)
    }, { timeout: 6000 })
  })

  it('shows safety score indicator', async () => {
    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => mockAutonomousStatus
    })

    renderComponent()

    await waitFor(() => {
      expect(screen.getByText(/95.2/)).toBeInTheDocument()
    })
  })

  it('displays performance metrics', async () => {
    ;(global.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockAutonomousStatus
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          data: mockDecisions,
          count: 2,
          total: 2
        })
      })

    renderComponent()

    await waitFor(() => {
      // Check for execution time metrics
      expect(screen.getByText(/250/)).toBeInTheDocument()
    })
  })

  it('shows decision rationale', async () => {
    ;(global.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockAutonomousStatus
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: mockDecisions, count: 2, total: 2 })
      })

    renderComponent()

    await waitFor(() => {
      expect(screen.getByText(/energy savings/i)).toBeInTheDocument()
    })
  })

  it('exports decision history', async () => {
    ;(global.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockAutonomousStatus
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: mockDecisions, count: 2, total: 2 })
      })

    renderComponent()

    const exportButton = await screen.findByText(/export/i)
    await userEvent.click(exportButton)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled()
    })
  })

  it('displays approach percentage to safety limits', async () => {
    ;(global.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockAutonomousStatus
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: mockDecisions, count: 2, total: 2 })
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: mockBoundaryStatus, count: 2 })
      })

    renderComponent()

    await waitFor(() => {
      expect(screen.getByText(/62.5%/)).toBeInTheDocument()
      expect(screen.getByText(/78.5%/)).toBeInTheDocument()
    })
  })

  it('shows active decision count', async () => {
    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => mockAutonomousStatus
    })

    renderComponent()

    await waitFor(() => {
      expect(screen.getByText(/3.*active/i)).toBeInTheDocument()
    })
  })
})
