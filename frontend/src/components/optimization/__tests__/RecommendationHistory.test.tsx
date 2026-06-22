import { render, screen, fireEvent, waitFor } from '@/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { RecommendationHistory } from '../RecommendationHistory'
import * as optimization from '@/lib/api/optimization'

vi.mock('@/lib/api/optimization', () => ({
  optimizationApi: {
    getHistory: vi.fn(),
  },
}))

describe('RecommendationHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders history table with executed recommendations', async () => {
    vi.mocked(optimization.optimizationApi.getHistory).mockResolvedValue({
      recommendations: [
        {
          id: 'rec-1',
          site_id: 'site-002',
          action_type: 'Adjust Setpoint',
          action: { point: 'temperature_setpoint', value: 21.5, unit: '°C' },
          risk_level: 'low',
          target_equipment: 'CHILLER-001',
          reason: 'Temperature trending down',
          expected_impact: {
            cost_zar: 150.0,
            comfort_delta: 0.5,
            energy_kwh: 5.0,
            temperature_c: 21.5,
          },
          confidence: 'high',
          profile: 'cost_saving',
          multi_objective_score: 0.85,
          status: 'executed',
          timestamp: new Date().toISOString(),
          actual_saving_kwh: 1.2,
          actual_saving_zar: 3.54,
          outcome: {
            predicted: { temperature_c: 21.5 },
            actual: { temperature_c: 21.3 },
            accuracy: 0.95,
          },
        },
      ],
    })

    render(<RecommendationHistory siteId="site-002" />)

    await waitFor(() => {
      expect(screen.getByText(/Temperature Setpoint to 21.5°C/)).toBeInTheDocument()
    })

    expect(screen.getAllByText(/CHILLER-001/).length).toBeGreaterThan(0)
    expect(screen.getByText(/executed/)).toBeInTheDocument()
  })

  it('filters by status', async () => {
    vi.mocked(optimization.optimizationApi.getHistory)
      .mockResolvedValueOnce({
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
            status: 'executed',
            timestamp: new Date().toISOString(),
          },
        ],
      })
      .mockResolvedValueOnce({
        recommendations: [
          {
            id: 'rec-2',
            site_id: 'site-002',
            action_type: 'Increase Flow',
            risk_level: 'medium',
            target_equipment: 'PUMP-001',
            reason: 'Low flow detected',
            expected_impact: {
              cost_zar: 50.0,
              comfort_delta: 0.2,
              energy_kwh: 2.0,
            },
            confidence: 'medium',
            profile: 'comfort_first',
            multi_objective_score: 0.72,
            status: 'rejected',
            timestamp: new Date().toISOString(),
          },
        ],
      })

    render(<RecommendationHistory siteId="site-002" />)

    // Initial render with "all" filter
    await waitFor(() => {
      expect(screen.getByText(/Adjust Setpoint/)).toBeInTheDocument()
    })

    // Click executed filter
    const executedButton = screen.getByRole('button', { name: /Executed/ })
    fireEvent.click(executedButton)

    await waitFor(() => {
      expect(optimization.optimizationApi.getHistory).toHaveBeenCalledWith(
        'site-002',
        { status: 'executed' }
      )
    })

    // Click rejected filter
    const rejectedButton = screen.getByRole('button', { name: /Rejected/ })
    fireEvent.click(rejectedButton)

    await waitFor(() => {
      expect(optimization.optimizationApi.getHistory).toHaveBeenCalledWith(
        'site-002',
        { status: 'rejected' }
      )
    })
  })

  it('displays measured recommendation outcome metrics', async () => {
    vi.mocked(optimization.optimizationApi.getHistory).mockResolvedValue({
      recommendations: [
        {
          id: 'rec-1',
          site_id: 'site-002',
          action_type: 'Adjust Setpoint',
          action: { point: 'temperature_setpoint', value: 21.5, unit: '°C' },
          risk_level: 'low',
          target_equipment: 'CHILLER-001',
          reason: 'Temperature trending down',
          expected_impact: {
            cost_zar: 150.0,
            comfort_delta: 0.5,
            energy_kwh: 5.0,
            temperature_c: 21.5,
          },
          confidence: 'high',
          profile: 'cost_saving',
          multi_objective_score: 0.85,
          status: 'executed',
          timestamp: new Date().toISOString(),
          baseline_energy_kwh: 5.43,
          actual_energy_kwh: 4.91,
          actual_saving_kwh: 0.52,
          actual_saving_zar: 1.53,
          outcome: {
            predicted: { temperature_c: 21.5 },
            actual: { temperature_c: 21.3 },
            accuracy: 0.95,
          },
        },
      ],
    })

    render(<RecommendationHistory siteId="site-002" />)

    await waitFor(() => {
      expect(screen.getAllByText(/\+0,52 kWh/).length).toBeGreaterThan(0)
    })

    expect(screen.getAllByText(/R\s*1,53/).length).toBeGreaterThan(0)
    expect(screen.getByText(/5,43 kWh/)).toBeInTheDocument()
    expect(screen.getAllByText(/21.5/).length).toBeGreaterThan(0)
  })

  it('shows no results message when empty', async () => {
    vi.mocked(optimization.optimizationApi.getHistory).mockResolvedValue({
      recommendations: [],
    })

    render(<RecommendationHistory siteId="site-002" />)

    await waitFor(() => {
      expect(
        screen.getByText('No recommendations found')
      ).toBeInTheDocument()
    })
  })

  it('displays pending outcome', async () => {
    vi.mocked(optimization.optimizationApi.getHistory).mockResolvedValue({
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
          status: 'executed',
          timestamp: new Date().toISOString(),
        },
      ],
    })

    render(<RecommendationHistory siteId="site-002" />)

    await waitFor(() => {
      expect(screen.getByText('Awaiting 30 min verification')).toBeInTheDocument()
    })
  })
})
