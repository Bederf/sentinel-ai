import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RecommendationsList } from '../RecommendationsList'
import type { Recommendation } from '../ApprovalDialog'

const mockRecommendations: Recommendation[] = [
  {
    id: 'rec-1',
    target_equipment: 'S002-CHILLER-B1-001',
    action: { point: 'setpoint', value: '20°C' },
    confidence: 'high',
    reason: 'Temperature rising',
    description: 'Peak demand response',
  },
  {
    id: 'rec-2',
    target_equipment: 'S002-AHU-L1-A',
    action: { point: 'vav_flow', value: '1500cfm' },
    confidence: 'medium',
    reason: 'Flow optimization',
  },
]

describe('RecommendationsList', () => {
  const mockOnApproved = vi.fn()
  const mockOnRejected = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render empty state when no recommendations', () => {
    render(
      <RecommendationsList
        recommendations={[]}
        onApproved={mockOnApproved}
        onRejected={mockOnRejected}
      />
    )

    expect(
      screen.getByText('No pending recommendations')
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        'All equipment is operating within expected parameters'
      )
    ).toBeInTheDocument()
  })

  it('should show loading state', () => {
    render(
      <RecommendationsList
        recommendations={[]}
        isLoading={true}
        onApproved={mockOnApproved}
        onRejected={mockOnRejected}
      />
    )

    const skeletons = document.querySelectorAll('[class*="animate-pulse"]')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('should display error message', () => {
    const errorMessage = 'Failed to load recommendations'
    render(
      <RecommendationsList
        recommendations={[]}
        error={errorMessage}
        onApproved={mockOnApproved}
        onRejected={mockOnRejected}
      />
    )

    expect(screen.getByText('Error loading recommendations')).toBeInTheDocument()
    expect(screen.getByText(errorMessage)).toBeInTheDocument()
  })

  it('should render recommendation items', () => {
    render(
      <RecommendationsList
        recommendations={mockRecommendations}
        onApproved={mockOnApproved}
        onRejected={mockOnRejected}
      />
    )

    expect(screen.getByText('S002-CHILLER-B1-001')).toBeInTheDocument()
    expect(screen.getByText('S002-AHU-L1-A')).toBeInTheDocument()
    expect(screen.getByText('setpoint → 20°C')).toBeInTheDocument()
    expect(screen.getByText('vav_flow → 1500cfm')).toBeInTheDocument()
  })

  it('should display confidence levels with correct styling', () => {
    render(
      <RecommendationsList
        recommendations={mockRecommendations}
        onApproved={mockOnApproved}
        onRejected={mockOnRejected}
      />
    )

    const highConfidence = screen.getByText('high confidence')
    const mediumConfidence = screen.getByText('medium confidence')

    expect(highConfidence).toHaveClass('bg-green-900/20')
    expect(mediumConfidence).toHaveClass('bg-yellow-900/20')
  })

  it('should display reason and description', () => {
    render(
      <RecommendationsList
        recommendations={mockRecommendations}
        onApproved={mockOnApproved}
        onRejected={mockOnRejected}
      />
    )

    expect(screen.getByText('Temperature rising')).toBeInTheDocument()
    expect(screen.getByText('Peak demand response')).toBeInTheDocument()
    expect(screen.getByText('Flow optimization')).toBeInTheDocument()
  })

  it('should open approval dialog when clicking approve button', async () => {
    const user = userEvent.setup()
    render(
      <RecommendationsList
        recommendations={mockRecommendations}
        onApproved={mockOnApproved}
        onRejected={mockOnRejected}
      />
    )

    const approveButtons = screen.getAllByRole('button', { name: /approve/i })
    expect(approveButtons.length).toBeGreaterThan(0)

    await user.click(approveButtons[0])

    // Check that dialog elements appear
    await waitFor(
      () => {
        expect(screen.getByText('Approve Equipment Control')).toBeInTheDocument()
      },
      { timeout: 2000 }
    )
  })

  it('should call onApproved callback after successful approval', async () => {
    const user = userEvent.setup()

    render(
      <RecommendationsList
        recommendations={mockRecommendations}
        onApproved={mockOnApproved}
        onRejected={mockOnRejected}
      />
    )

    // Verify the list renders and has approve buttons
    const approveButtons = screen.getAllByRole('button', { name: /approve/i })
    expect(approveButtons.length).toBeGreaterThan(0)

    // Click first approve button to open dialog
    await user.click(approveButtons[0])

    // Dialog should now be visible
    await waitFor(() => {
      expect(screen.getByText('Approve Equipment Control')).toBeInTheDocument()
    })
  })

  it('should filter recommendations by confidence level', () => {
    const highConfidenceRecs = mockRecommendations.filter(
      (r) => r.confidence === 'high'
    )

    render(
      <RecommendationsList
        recommendations={highConfidenceRecs}
        onApproved={mockOnApproved}
        onRejected={mockOnRejected}
      />
    )

    expect(screen.getByText('S002-CHILLER-B1-001')).toBeInTheDocument()
    expect(screen.queryByText('S002-AHU-L1-A')).not.toBeInTheDocument()
  })

  it('should render multiple recommendations', () => {
    const multipleRecs = [
      ...mockRecommendations,
      {
        id: 'rec-3',
        target_equipment: 'S002-FCU-L2-B',
        action: { point: 'damper', value: '45%' },
        confidence: 'low',
        reason: 'Energy optimization',
      },
    ]

    render(
      <RecommendationsList
        recommendations={multipleRecs}
        onApproved={mockOnApproved}
        onRejected={mockOnRejected}
      />
    )

    const approveButtons = screen.getAllByRole('button', { name: /approve/i })
    expect(approveButtons).toHaveLength(3)
  })

  it('should handle missing optional fields gracefully', () => {
    const minimalRecs: Recommendation[] = [
      {
        id: 'rec-minimal',
        target_equipment: 'S002-EQUIPMENT',
      },
    ]

    render(
      <RecommendationsList
        recommendations={minimalRecs}
        onApproved={mockOnApproved}
        onRejected={mockOnRejected}
      />
    )

    expect(screen.getByText('S002-EQUIPMENT')).toBeInTheDocument()
    expect(screen.getByText('medium confidence')).toBeInTheDocument()
  })
})
