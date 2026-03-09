import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AutonomousDecisionPanel } from '../AutonomousDecisionPanel'

// Mock the api module
vi.mock('@/lib/api', () => ({
  api: {
    getAutonomousDecisions: vi.fn(),
  },
}))

import { api } from '@/lib/api'

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
    escalation_level: 0,
  },
  {
    id: 'dec-002',
    device_id: 'lighting_001',
    device_name: 'Lighting Zone 1',
    point_name: 'brightness',
    current_value: 85,
    target_value: 75,
    status: 'blocked',
    decision_rationale: 'Brightness reduction - low occupancy',
    timestamp: new Date().toISOString(),
    execution_time_ms: 150,
    escalation_level: 2,
  },
  {
    id: 'dec-003',
    device_id: 'hvac_002',
    device_name: 'HVAC Unit 2',
    point_name: 'fan_speed',
    current_value: 80,
    target_value: 60,
    status: 'executing',
    decision_rationale: null,
    timestamp: new Date().toISOString(),
    execution_time_ms: null,
    escalation_level: 1,
  },
]

describe('AutonomousDecisionPanel', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.mocked(api.getAutonomousDecisions).mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders the panel heading', () => {
    vi.mocked(api.getAutonomousDecisions).mockResolvedValue({ data: [] })
    render(<AutonomousDecisionPanel autoRefresh={false} />)
    expect(screen.getByText('Autonomous Decisions')).toBeInTheDocument()
  })

  it('shows loading state while fetching', () => {
    vi.mocked(api.getAutonomousDecisions).mockReturnValue(new Promise(() => {}))
    render(<AutonomousDecisionPanel />)
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  it('shows empty state when no decisions exist', async () => {
    vi.mocked(api.getAutonomousDecisions).mockResolvedValue({ data: [] })
    render(<AutonomousDecisionPanel />)

    await waitFor(() => {
      expect(screen.getByText(/no autonomous decisions yet/i)).toBeInTheDocument()
    })
  })

  it('displays decision device names', async () => {
    vi.mocked(api.getAutonomousDecisions).mockResolvedValue({ data: mockDecisions })
    render(<AutonomousDecisionPanel />)

    await waitFor(() => {
      expect(screen.getByText('HVAC Unit 1')).toBeInTheDocument()
      expect(screen.getByText('Lighting Zone 1')).toBeInTheDocument()
      expect(screen.getByText('HVAC Unit 2')).toBeInTheDocument()
    })
  })

  it('displays point values with arrow notation', async () => {
    vi.mocked(api.getAutonomousDecisions).mockResolvedValue({ data: mockDecisions })
    render(<AutonomousDecisionPanel />)

    await waitFor(() => {
      expect(screen.getByText(/cooling_setpoint.*22.*23\.5/)).toBeInTheDocument()
      expect(screen.getByText(/brightness.*85.*75/)).toBeInTheDocument()
    })
  })

  it('shows decision rationale when present', async () => {
    vi.mocked(api.getAutonomousDecisions).mockResolvedValue({ data: mockDecisions })
    render(<AutonomousDecisionPanel />)

    await waitFor(() => {
      expect(screen.getByText(/temperature optimization for energy savings/i)).toBeInTheDocument()
      expect(screen.getByText(/brightness reduction/i)).toBeInTheDocument()
    })
  })

  it('truncates long rationale text to 100 characters', async () => {
    const longRationale = 'A'.repeat(150)
    vi.mocked(api.getAutonomousDecisions).mockResolvedValue({
      data: [{ ...mockDecisions[0], decision_rationale: longRationale }],
    })
    render(<AutonomousDecisionPanel />)

    await waitFor(() => {
      expect(screen.getByText(/\.\.\.$/)).toBeInTheDocument()
    })
  })

  it('shows execution time when available', async () => {
    vi.mocked(api.getAutonomousDecisions).mockResolvedValue({
      data: [mockDecisions[0]],
    })
    render(<AutonomousDecisionPanel />)

    await waitFor(() => {
      expect(screen.getByText(/250\.0ms/)).toBeInTheDocument()
    })
  })

  it('does not show execution time when null', async () => {
    vi.mocked(api.getAutonomousDecisions).mockResolvedValue({
      data: [mockDecisions[2]], // execution_time_ms is null
    })
    render(<AutonomousDecisionPanel />)

    await waitFor(() => {
      expect(screen.getByText('HVAC Unit 2')).toBeInTheDocument()
    })
    expect(screen.queryByText(/executed in/i)).not.toBeInTheDocument()
  })

  it('shows escalation badges', async () => {
    vi.mocked(api.getAutonomousDecisions).mockResolvedValue({ data: mockDecisions })
    render(<AutonomousDecisionPanel />)

    await waitFor(() => {
      expect(screen.getByText('None')).toBeInTheDocument()       // level 0
      expect(screen.getByText('Alert')).toBeInTheDocument()      // level 2
      expect(screen.getByText('Warning')).toBeInTheDocument()    // level 1
    })
  })

  it('calls api with limit parameter', async () => {
    vi.mocked(api.getAutonomousDecisions).mockResolvedValue({ data: [] })
    render(<AutonomousDecisionPanel />)

    await waitFor(() => {
      expect(api.getAutonomousDecisions).toHaveBeenCalledWith({ limit: 10 })
    })
  })

  it('refreshes on button click', async () => {
    vi.mocked(api.getAutonomousDecisions).mockResolvedValue({ data: [] })
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(<AutonomousDecisionPanel autoRefresh={false} />)

    // Wait for initial empty state
    await waitFor(() => {
      expect(screen.getByText(/no autonomous decisions yet/i)).toBeInTheDocument()
    })

    vi.mocked(api.getAutonomousDecisions).mockClear()
    vi.mocked(api.getAutonomousDecisions).mockResolvedValue({ data: mockDecisions })

    const refreshButton = screen.getByText(/refresh history/i)
    await user.click(refreshButton)

    await waitFor(() => {
      expect(api.getAutonomousDecisions).toHaveBeenCalled()
    })
  })

  it('auto-refreshes at the specified interval', async () => {
    vi.mocked(api.getAutonomousDecisions).mockResolvedValue({ data: [] })
    render(<AutonomousDecisionPanel autoRefresh={true} refreshInterval={3000} />)

    await waitFor(() => {
      expect(api.getAutonomousDecisions).toHaveBeenCalledTimes(1)
    })

    vi.advanceTimersByTime(3000)

    await waitFor(() => {
      expect(api.getAutonomousDecisions).toHaveBeenCalledTimes(2)
    })
  })

  it('does not auto-refresh when autoRefresh is false', async () => {
    vi.mocked(api.getAutonomousDecisions).mockResolvedValue({ data: [] })
    render(<AutonomousDecisionPanel autoRefresh={false} />)

    // Should not call at all when autoRefresh is false
    vi.advanceTimersByTime(10000)
    expect(api.getAutonomousDecisions).not.toHaveBeenCalled()
  })

  it('handles API errors gracefully without crashing', async () => {
    vi.mocked(api.getAutonomousDecisions).mockRejectedValue(new Error('Network error'))
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    render(<AutonomousDecisionPanel />)

    await waitFor(() => {
      // After error, loading finishes and empty state is shown
      expect(screen.getByText(/no autonomous decisions yet/i)).toBeInTheDocument()
    })

    expect(consoleSpy).toHaveBeenCalledWith(
      'Failed to fetch autonomous decisions:',
      expect.any(Error)
    )
    consoleSpy.mockRestore()
  })

  it('renders the Refresh History button', async () => {
    vi.mocked(api.getAutonomousDecisions).mockResolvedValue({ data: [] })
    render(<AutonomousDecisionPanel autoRefresh={false} />)

    expect(screen.getByText(/refresh history/i)).toBeInTheDocument()
  })

  it('renders multiple decisions in order', async () => {
    vi.mocked(api.getAutonomousDecisions).mockResolvedValue({ data: mockDecisions })
    render(<AutonomousDecisionPanel />)

    await waitFor(() => {
      const items = screen.getAllByText(/cooling_setpoint|brightness|fan_speed/)
      expect(items).toHaveLength(3)
    })
  })

  it('cleans up interval on unmount', async () => {
    vi.mocked(api.getAutonomousDecisions).mockResolvedValue({ data: [] })
    const { unmount } = render(<AutonomousDecisionPanel autoRefresh={true} refreshInterval={3000} />)

    await waitFor(() => {
      expect(api.getAutonomousDecisions).toHaveBeenCalledTimes(1)
    })

    unmount()

    vi.mocked(api.getAutonomousDecisions).mockClear()
    vi.advanceTimersByTime(6000)

    // Should not have been called after unmount
    expect(api.getAutonomousDecisions).not.toHaveBeenCalled()
  })

  it('does not render rationale div when rationale is null', async () => {
    vi.mocked(api.getAutonomousDecisions).mockResolvedValue({
      data: [mockDecisions[2]], // rationale is null
    })
    render(<AutonomousDecisionPanel />)

    await waitFor(() => {
      expect(screen.getByText('HVAC Unit 2')).toBeInTheDocument()
    })

    // No italic rationale text should be present
    const container = screen.getByText('HVAC Unit 2').closest('.border')
    const italicElements = container?.querySelectorAll('.italic')
    expect(italicElements?.length ?? 0).toBe(0)
  })
})
