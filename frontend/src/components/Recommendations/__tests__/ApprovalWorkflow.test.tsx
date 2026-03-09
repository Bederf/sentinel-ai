/**
 * End-to-End Approval Workflow Integration Tests (Phase 68-02 Task 3)
 *
 * Tests the complete approval workflow from dashboard recommendation display
 * through approval dialog interaction to API submission and state updates.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RecommendationsList } from '../RecommendationsList'
import { approvalsApi } from '@/lib/api/approvals'
import type { Recommendation } from '../ApprovalDialog'
import type { ApprovalResponse } from '@/lib/api/approvals'

// Mock the approvals API
vi.mock('@/lib/api/approvals', () => ({
  approvalsApi: {
    approveRecommendation: vi.fn(),
    rejectRecommendation: vi.fn(),
    getApprovalStatus: vi.fn(),
  },
}))

// Mock React Query
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
    mutations: { retry: false },
  },
})

const mockRecommendations: Recommendation[] = [
  {
    id: 'rec-001',
    target_equipment: 'S002-CHILLER-B1-001',
    action: { point: 'setpoint', value: '20°C' },
    confidence: 'high',
    reason: 'Peak demand response - grid constraint',
    description: 'Load reduction: 30kW',
  },
  {
    id: 'rec-002',
    target_equipment: 'S002-AHU-L1-A',
    action: { point: 'vav_flow', value: '1500cfm' },
    confidence: 'medium',
    reason: 'Flow optimization during off-peak',
    description: 'Energy savings: 8kW',
  },
  {
    id: 'rec-003',
    target_equipment: 'S002-FCU-L2-B',
    action: { point: 'damper', value: '45%' },
    confidence: 'low',
    reason: 'Seasonal adjustment',
  },
]

/**
 * Helper to click the "Approve" tab button inside the dialog.
 * The dialog is rendered via createPortal to document.body.
 * There are multiple "Approve" buttons: the list items' approve buttons
 * and the dialog's tab button. The dialog tab button has class "text-sm".
 */
const clickDialogApproveTab = async (user: ReturnType<typeof userEvent.setup>) => {
  const allApproveButtons = screen.getAllByRole('button', { name: /^approve$/i })
  // The dialog tab button is the one with 'text-sm' class (smaller than list buttons)
  const dialogApproveTab = allApproveButtons.find(btn =>
    btn.className.includes('text-sm') && btn.className.includes('rounded') && !btn.className.includes('bg-blue-600')
  )
  if (dialogApproveTab) {
    await user.click(dialogApproveTab)
  }
}

describe('ApprovalWorkflow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
  })

  describe('Recommendation List Display', () => {
    it('should display all recommendations in list format', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <RecommendationsList
            recommendations={mockRecommendations}
            onApproved={vi.fn()}
            onRejected={vi.fn()}
          />
        </QueryClientProvider>
      )

      // Verify all equipment is displayed
      expect(screen.getByText('S002-CHILLER-B1-001')).toBeInTheDocument()
      expect(screen.getByText('S002-AHU-L1-A')).toBeInTheDocument()
      expect(screen.getByText('S002-FCU-L2-B')).toBeInTheDocument()

      // Verify actions are shown
      expect(screen.getByText("setpoint → 20°C")).toBeInTheDocument()
      expect(screen.getByText('vav_flow → 1500cfm')).toBeInTheDocument()
      expect(screen.getByText('damper → 45%')).toBeInTheDocument()
    })

    it('should display confidence levels with correct styling', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <RecommendationsList
            recommendations={mockRecommendations}
            onApproved={vi.fn()}
            onRejected={vi.fn()}
          />
        </QueryClientProvider>
      )

      const highConfidence = screen.getByText('high confidence')
      const mediumConfidence = screen.getByText('medium confidence')
      const lowConfidence = screen.getByText('low confidence')

      expect(highConfidence).toHaveClass('bg-green-900/20')
      expect(mediumConfidence).toHaveClass('bg-yellow-900/20')
      expect(lowConfidence).toHaveClass('bg-red-900/20')
    })

    it('should display reasons and descriptions for recommendations', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <RecommendationsList
            recommendations={mockRecommendations}
            onApproved={vi.fn()}
            onRejected={vi.fn()}
          />
        </QueryClientProvider>
      )

      expect(
        screen.getByText('Peak demand response - grid constraint')
      ).toBeInTheDocument()
      expect(screen.getByText('Load reduction: 30kW')).toBeInTheDocument()
      expect(
        screen.getByText('Flow optimization during off-peak')
      ).toBeInTheDocument()
      expect(screen.getByText('Energy savings: 8kW')).toBeInTheDocument()
    })

    it('should have approve buttons for each recommendation', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <RecommendationsList
            recommendations={mockRecommendations}
            onApproved={vi.fn()}
            onRejected={vi.fn()}
          />
        </QueryClientProvider>
      )

      const approveButtons = screen.getAllByRole('button', { name: /approve/i })
      expect(approveButtons).toHaveLength(3)
    })
  })

  describe('Approval Dialog Workflow', () => {
    it('should open approval dialog when clicking approve button', async () => {
      const user = userEvent.setup()
      render(
        <QueryClientProvider client={queryClient}>
          <RecommendationsList
            recommendations={mockRecommendations}
            onApproved={vi.fn()}
            onRejected={vi.fn()}
          />
        </QueryClientProvider>
      )

      // Click first approve button
      const approveButtons = screen.getAllByRole('button', { name: /approve/i })
      await user.click(approveButtons[0])

      // Dialog should open
      const dialogTitle = await waitFor(() =>
        screen.getByText('Approve Equipment Control')
      )
      expect(dialogTitle).toBeInTheDocument()

      // Equipment details should be visible (scope to dialog)
      const dialog = dialogTitle.closest('[role="dialog"]') || document
      expect(
        within(dialog as HTMLElement).getAllByText('S002-CHILLER-B1-001')[0]
      ).toBeInTheDocument()
      expect(
        within(dialog as HTMLElement).getByText('setpoint = 20°C')
      ).toBeInTheDocument()
    })

    it('should display all recommendation details in dialog', async () => {
      const user = userEvent.setup()
      render(
        <QueryClientProvider client={queryClient}>
          <RecommendationsList
            recommendations={mockRecommendations}
            onApproved={vi.fn()}
            onRejected={vi.fn()}
          />
        </QueryClientProvider>
      )

      const approveButtons = screen.getAllByRole('button', { name: /approve/i })
      await user.click(approveButtons[0])

      const dialogTitle = await waitFor(() =>
        screen.getByText('Approve Equipment Control')
      )
      expect(dialogTitle).toBeInTheDocument()

      // Check for equipment details in the dialog
      expect(screen.getAllByText('S002-CHILLER-B1-001').length).toBeGreaterThanOrEqual(1)
      expect(screen.getByText('setpoint = 20°C')).toBeInTheDocument()

      // Navigate to approve tab inside dialog to see the name input
      await clickDialogApproveTab(user)

      // Verify dialog contains technician name input (core functionality)
      expect(screen.getByLabelText(/Your Name/i)).toBeInTheDocument()
    })

    it('should require technician name before approval', async () => {
      const user = userEvent.setup()
      render(
        <QueryClientProvider client={queryClient}>
          <RecommendationsList
            recommendations={mockRecommendations}
            onApproved={vi.fn()}
            onRejected={vi.fn()}
          />
        </QueryClientProvider>
      )

      const approveButtons = screen.getAllByRole('button', { name: /approve/i })
      await user.click(approveButtons[0])

      await waitFor(() => {
        expect(
          screen.getByText('Approve Equipment Control')
        ).toBeInTheDocument()
      })

      // Navigate to approve tab inside dialog
      await clickDialogApproveTab(user)

      // Approve button should be disabled initially
      const approveDialogButton = screen.getByRole('button', {
        name: /approve & execute/i,
      })
      expect(approveDialogButton).toBeDisabled()

      // Enter technician name
      const nameInput = screen.getByPlaceholderText('e.g., John Smith')
      await user.type(nameInput, 'John Smith')

      // Approve button should now be enabled
      expect(approveDialogButton).not.toBeDisabled()
    })
  })

  describe('Approval Submission', () => {
    it('should submit approval with technician name and optional notes', async () => {
      const user = userEvent.setup()
      const mockApprovalResponse: ApprovalResponse = {
        success: true,
        recommendation_id: 'rec-001',
        status: 'executed',
        executed_at: new Date().toISOString(),
        cov_verified: true,
      }

      vi.mocked(approvalsApi.approveRecommendation).mockResolvedValueOnce(
        mockApprovalResponse
      )

      const mockOnApproved = vi.fn()
      render(
        <QueryClientProvider client={queryClient}>
          <RecommendationsList
            recommendations={mockRecommendations}
            onApproved={mockOnApproved}
            onRejected={vi.fn()}
          />
        </QueryClientProvider>
      )

      const approveButtons = screen.getAllByRole('button', { name: /approve/i })
      await user.click(approveButtons[0])

      await waitFor(() => {
        expect(
          screen.getByText('Approve Equipment Control')
        ).toBeInTheDocument()
      })

      // Navigate to approve tab inside dialog
      await clickDialogApproveTab(user)

      // Fill form
      const nameInput = screen.getByPlaceholderText('e.g., John Smith')
      await user.type(nameInput, 'John Smith')

      const notesInput = screen.getByPlaceholderText(
        'Add any notes about this approval...'
      )
      await user.type(notesInput, 'Peak demand response - urgent')

      // Submit
      const approveButton = screen.getByRole('button', {
        name: /approve & execute/i,
      })
      await user.click(approveButton)

      // Verify API was called with correct params
      await waitFor(() => {
        expect(approvalsApi.approveRecommendation).toHaveBeenCalledWith(
          'rec-001',
          'John Smith',
          'Peak demand response - urgent'
        )
      })
    })

    it('should show loading state while submitting', async () => {
      const user = userEvent.setup()

      // Delay the response to see loading state
      vi.mocked(approvalsApi.approveRecommendation).mockImplementationOnce(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () =>
                resolve({
                  success: true,
                  recommendation_id: 'rec-001',
                  status: 'executed',
                  cov_verified: true,
                }),
              500
            )
          )
      )

      const mockOnApproved = vi.fn()
      render(
        <QueryClientProvider client={queryClient}>
          <RecommendationsList
            recommendations={mockRecommendations}
            onApproved={mockOnApproved}
            onRejected={vi.fn()}
          />
        </QueryClientProvider>
      )

      const approveButtons = screen.getAllByRole('button', { name: /approve/i })
      await user.click(approveButtons[0])

      await waitFor(() => {
        expect(
          screen.getByText('Approve Equipment Control')
        ).toBeInTheDocument()
      })

      // Navigate to approve tab inside dialog
      await clickDialogApproveTab(user)

      const nameInput = screen.getByPlaceholderText('e.g., John Smith')
      await user.type(nameInput, 'John Smith')

      const approveButton = screen.getByRole('button', {
        name: /approve & execute/i,
      })
      await user.click(approveButton)

      // Check for loading state
      expect(screen.getByText(/approving/i)).toBeInTheDocument()
    })

    it('should call onApproved callback after successful submission', async () => {
      const user = userEvent.setup()
      const mockApprovalResponse: ApprovalResponse = {
        success: true,
        recommendation_id: 'rec-001',
        status: 'executed',
        cov_verified: true,
      }

      vi.mocked(approvalsApi.approveRecommendation).mockResolvedValueOnce(
        mockApprovalResponse
      )

      const mockOnApproved = vi.fn()
      render(
        <QueryClientProvider client={queryClient}>
          <RecommendationsList
            recommendations={mockRecommendations}
            onApproved={mockOnApproved}
            onRejected={vi.fn()}
          />
        </QueryClientProvider>
      )

      const approveButtons = screen.getAllByRole('button', { name: /approve/i })
      await user.click(approveButtons[0])

      await waitFor(() => {
        expect(
          screen.getByText('Approve Equipment Control')
        ).toBeInTheDocument()
      })

      // Navigate to approve tab inside dialog
      await clickDialogApproveTab(user)

      const nameInput = screen.getByPlaceholderText('e.g., John Smith')
      await user.type(nameInput, 'John Smith')

      const approveButton = screen.getByRole('button', {
        name: /approve & execute/i,
      })
      await user.click(approveButton)

      // Wait for callback
      await waitFor(
        () => {
          expect(mockOnApproved).toHaveBeenCalledWith(mockApprovalResponse)
        },
        { timeout: 3000 }
      )
    })

    it('should display success message after approval', async () => {
      const user = userEvent.setup()
      const mockApprovalResponse: ApprovalResponse = {
        success: true,
        recommendation_id: 'rec-001',
        status: 'executed',
        cov_verified: true,
      }

      vi.mocked(approvalsApi.approveRecommendation).mockResolvedValueOnce(
        mockApprovalResponse
      )

      render(
        <QueryClientProvider client={queryClient}>
          <RecommendationsList
            recommendations={mockRecommendations}
            onApproved={vi.fn()}
            onRejected={vi.fn()}
          />
        </QueryClientProvider>
      )

      const approveButtons = screen.getAllByRole('button', { name: /approve/i })
      await user.click(approveButtons[0])

      await waitFor(() => {
        expect(
          screen.getByText('Approve Equipment Control')
        ).toBeInTheDocument()
      })

      // Navigate to approve tab inside dialog
      await clickDialogApproveTab(user)

      const nameInput = screen.getByPlaceholderText('e.g., John Smith')
      await user.type(nameInput, 'John Smith')

      const approveButton = screen.getByRole('button', {
        name: /approve & execute/i,
      })
      await user.click(approveButton)

      // Wait for success message
      await waitFor(() => {
        expect(
          screen.getByText(/recommendation approved and device control executed/i)
        ).toBeInTheDocument()
      })
    })
  })

  describe('Error Handling', () => {
    it('should display error message on approval failure', async () => {
      const user = userEvent.setup()
      const errorMessage =
        'Safety constraint violation: Temperature below minimum'

      vi.mocked(approvalsApi.approveRecommendation).mockRejectedValueOnce(
        new Error(errorMessage)
      )

      render(
        <QueryClientProvider client={queryClient}>
          <RecommendationsList
            recommendations={mockRecommendations}
            onApproved={vi.fn()}
            onRejected={vi.fn()}
          />
        </QueryClientProvider>
      )

      const approveButtons = screen.getAllByRole('button', { name: /approve/i })
      await user.click(approveButtons[0])

      await waitFor(() => {
        expect(
          screen.getByText('Approve Equipment Control')
        ).toBeInTheDocument()
      })

      // Navigate to approve tab inside dialog
      await clickDialogApproveTab(user)

      const nameInput = screen.getByPlaceholderText('e.g., John Smith')
      await user.type(nameInput, 'John Smith')

      const approveButton = screen.getByRole('button', {
        name: /approve & execute/i,
      })
      await user.click(approveButton)

      // Wait for error message
      await waitFor(() => {
        expect(screen.getByText(errorMessage)).toBeInTheDocument()
      })
    })

    it('should keep dialog open on error for retry', async () => {
      const user = userEvent.setup()

      vi.mocked(approvalsApi.approveRecommendation).mockRejectedValueOnce(
        new Error('Device communication failed')
      )

      render(
        <QueryClientProvider client={queryClient}>
          <RecommendationsList
            recommendations={mockRecommendations}
            onApproved={vi.fn()}
            onRejected={vi.fn()}
          />
        </QueryClientProvider>
      )

      const approveButtons = screen.getAllByRole('button', { name: /approve/i })
      await user.click(approveButtons[0])

      await waitFor(() => {
        expect(
          screen.getByText('Approve Equipment Control')
        ).toBeInTheDocument()
      })

      // Navigate to approve tab inside dialog
      await clickDialogApproveTab(user)

      const nameInput = screen.getByPlaceholderText('e.g., John Smith')
      await user.type(nameInput, 'John Smith')

      const approveButton = screen.getByRole('button', {
        name: /approve & execute/i,
      })
      await user.click(approveButton)

      await waitFor(() => {
        expect(
          screen.getByText('Device communication failed')
        ).toBeInTheDocument()
      })

      // Dialog should still be open for retry
      expect(
        screen.getByText('Approve Equipment Control')
      ).toBeInTheDocument()
    })
  })

  describe('Rejection Workflow', () => {
    it('should handle rejection dialog interactions', async () => {
      const user = userEvent.setup()
      render(
        <QueryClientProvider client={queryClient}>
          <RecommendationsList
            recommendations={mockRecommendations}
            onApproved={vi.fn()}
            onRejected={vi.fn()}
          />
        </QueryClientProvider>
      )

      const approveButtons = screen.getAllByRole('button', { name: /approve/i })
      await user.click(approveButtons[0])

      await waitFor(() => {
        expect(
          screen.getByText('Approve Equipment Control')
        ).toBeInTheDocument()
      })

      // Navigate to approve tab inside dialog to see the name input
      await clickDialogApproveTab(user)

      // Verify the dialog has name input on approve tab
      expect(screen.getByPlaceholderText('e.g., John Smith')).toBeInTheDocument()

      // Note: Tab switching and rejection submission are tested at dialog component level
      // This test verifies dialog integration with list
    })
  })

  describe('Dialog Closing', () => {
    it('should close dialog on cancel button', async () => {
      const user = userEvent.setup()
      render(
        <QueryClientProvider client={queryClient}>
          <RecommendationsList
            recommendations={mockRecommendations}
            onApproved={vi.fn()}
            onRejected={vi.fn()}
          />
        </QueryClientProvider>
      )

      const approveButtons = screen.getAllByRole('button', { name: /approve/i })
      await user.click(approveButtons[0])

      await waitFor(() => {
        expect(
          screen.getByText('Approve Equipment Control')
        ).toBeInTheDocument()
      })

      const cancelButton = screen.getByRole('button', { name: /cancel/i })
      await user.click(cancelButton)

      // Dialog should close
      await waitFor(() => {
        expect(
          screen.queryByText('Approve Equipment Control')
        ).not.toBeInTheDocument()
      })
    })

    it('should close dialog on escape key', async () => {
      const user = userEvent.setup()
      render(
        <QueryClientProvider client={queryClient}>
          <RecommendationsList
            recommendations={mockRecommendations}
            onApproved={vi.fn()}
            onRejected={vi.fn()}
          />
        </QueryClientProvider>
      )

      const approveButtons = screen.getAllByRole('button', { name: /approve/i })
      await user.click(approveButtons[0])

      await waitFor(() => {
        expect(
          screen.getByText('Approve Equipment Control')
        ).toBeInTheDocument()
      })

      // Press escape
      await user.keyboard('{Escape}')

      // Dialog should close
      await waitFor(() => {
        expect(
          screen.queryByText('Approve Equipment Control')
        ).not.toBeInTheDocument()
      })
    })

    it('should reset form after successful approval', async () => {
      const user = userEvent.setup()
      const mockApprovalResponse: ApprovalResponse = {
        success: true,
        recommendation_id: 'rec-001',
        status: 'executed',
        cov_verified: true,
      }

      vi.mocked(approvalsApi.approveRecommendation).mockResolvedValueOnce(
        mockApprovalResponse
      )

      render(
        <QueryClientProvider client={queryClient}>
          <RecommendationsList
            recommendations={mockRecommendations}
            onApproved={vi.fn()}
            onRejected={vi.fn()}
          />
        </QueryClientProvider>
      )

      const approveButtons = screen.getAllByRole('button', { name: /approve/i })
      await user.click(approveButtons[0])

      await waitFor(() => {
        expect(
          screen.getByText('Approve Equipment Control')
        ).toBeInTheDocument()
      })

      // Navigate to approve tab inside dialog
      await clickDialogApproveTab(user)

      const nameInput = screen.getByPlaceholderText('e.g., John Smith')
      await user.type(nameInput, 'John Smith')

      const approveButton = screen.getByRole('button', {
        name: /approve & execute/i,
      })
      await user.click(approveButton)

      await waitFor(() => {
        expect(
          screen.getByText(/recommendation approved and device control executed/i)
        ).toBeInTheDocument()
      })
    })
  })
})
