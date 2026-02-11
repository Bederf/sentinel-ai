import { render, screen, fireEvent, waitFor } from '@/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { RecommendationsDashboard } from '../RecommendationsDashboard'
import * as optimization from '@/lib/api/optimization'

vi.mock('@/lib/api/optimization', () => ({
  optimizationApi: {
    getPending: vi.fn(),
    approve: vi.fn(),
    reject: vi.fn(),
  },
}))

describe('RecommendationsDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders pending recommendations', async () => {
    vi.mocked(optimization.optimizationApi.getPending).mockResolvedValue({
      recommendations: [
        {
          id: 'rec-1',
          site_id: 'site-002',
          action_type: 'Adjust Setpoint',
          risk_level: 'low',
          target_equipment: 'CHILLER-001',
          reason: 'Temperature trending down',
          expected_impact: {
            cost_zar: 150.0,
            comfort_delta: 0.5,
            energy_kwh: 5.0,
          },
          confidence: 'high',
          profile: 'cost_saving',
          multi_objective_score: 0.85,
          status: 'pending',
          timestamp: new Date().toISOString(),
        },
      ],
    })

    render(<RecommendationsDashboard siteId="site-002" />)

    await waitFor(() => {
      expect(screen.getByText('Adjust Setpoint')).toBeInTheDocument()
    })

    expect(screen.getByText(/CHILLER-001/)).toBeInTheDocument()
    expect(screen.getByText(/Temperature trending down/)).toBeInTheDocument()
  })

  it('shows no recommendations message when empty', async () => {
    vi.mocked(optimization.optimizationApi.getPending).mockResolvedValue({
      recommendations: [],
    })

    render(<RecommendationsDashboard siteId="site-002" />)

    await waitFor(() => {
      expect(screen.getByText('No pending recommendations')).toBeInTheDocument()
    })
  })

  it('approves recommendation', async () => {
    vi.mocked(optimization.optimizationApi.getPending).mockResolvedValue({
      recommendations: [
        {
          id: 'rec-1',
          site_id: 'site-002',
          action_type: 'Adjust Setpoint',
          risk_level: 'low',
          target_equipment: 'CHILLER-001',
          reason: 'Temperature trending down',
          expected_impact: {
            cost_zar: 150.0,
            comfort_delta: 0.5,
            energy_kwh: 5.0,
          },
          confidence: 'high',
          profile: 'cost_saving',
          multi_objective_score: 0.85,
          status: 'pending',
          timestamp: new Date().toISOString(),
        },
      ],
    })

    vi.mocked(optimization.optimizationApi.approve).mockResolvedValue({})

    render(<RecommendationsDashboard siteId="site-002" />)

    await waitFor(() => {
      expect(screen.getByText(/Adjust Setpoint/)).toBeInTheDocument()
    })

    const approveButton = screen.getByRole('button', { name: /Approve/ })
    fireEvent.click(approveButton)

    await waitFor(() => {
      expect(optimization.optimizationApi.approve).toHaveBeenCalledWith(
        'rec-1',
        'User approved'
      )
    })
  })

  it('rejects recommendation with reason', async () => {
    vi.mocked(optimization.optimizationApi.getPending).mockResolvedValue({
      recommendations: [
        {
          id: 'rec-1',
          site_id: 'site-002',
          action_type: 'Adjust Setpoint',
          risk_level: 'low',
          target_equipment: 'CHILLER-001',
          reason: 'Temperature trending down',
          expected_impact: {
            cost_zar: 150.0,
            comfort_delta: 0.5,
            energy_kwh: 5.0,
          },
          confidence: 'high',
          profile: 'cost_saving',
          multi_objective_score: 0.85,
          status: 'pending',
          timestamp: new Date().toISOString(),
        },
      ],
    })

    vi.mocked(optimization.optimizationApi.reject).mockResolvedValue({})

    render(<RecommendationsDashboard siteId="site-002" />)

    await waitFor(() => {
      expect(screen.getByText(/Adjust Setpoint/)).toBeInTheDocument()
    })

    const rejectButton = screen.getByRole('button', { name: /Reject/ })
    fireEvent.click(rejectButton)

    const reasonInput = screen.getByPlaceholderText(
      'Why are you rejecting this recommendation?'
    ) as HTMLTextAreaElement
    fireEvent.change(reasonInput, { target: { value: 'Too risky' } })

    const confirmButton = screen.getByRole('button', { name: /Confirm Rejection/ })
    fireEvent.click(confirmButton)

    await waitFor(() => {
      expect(optimization.optimizationApi.reject).toHaveBeenCalledWith(
        'rec-1',
        'Too risky'
      )
    })
  })

  it('displays risk level badge', async () => {
    vi.mocked(optimization.optimizationApi.getPending).mockResolvedValue({
      recommendations: [
        {
          id: 'rec-1',
          site_id: 'site-002',
          action_type: 'Adjust Setpoint',
          risk_level: 'high',
          target_equipment: 'CHILLER-001',
          reason: 'Temperature trending down',
          expected_impact: {
            cost_zar: 150.0,
            comfort_delta: 0.5,
            energy_kwh: 5.0,
          },
          confidence: 'high',
          profile: 'cost_saving',
          multi_objective_score: 0.85,
          status: 'pending',
          timestamp: new Date().toISOString(),
        },
      ],
    })

    render(<RecommendationsDashboard siteId="site-002" />)

    await waitFor(() => {
      expect(screen.getByText(/high/)).toBeInTheDocument()
    })
  })
})
